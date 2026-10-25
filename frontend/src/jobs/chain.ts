import { createPublicClient, createWalletClient, custom, TransactionNotFoundError, type Abi, type Address, type Hash } from 'viem'
import { arbitrumSepolia } from 'viem/chains'

import contractArtifact from '../contracts/nebula.json'
import { ARBITRUM_SEPOLIA_CHAIN_ID, CONTRACT_ADDRESS } from '../utils/constants'
import type { Eip1193Provider } from '../wallet/wallet'
import { WrongChainError } from '../wallet/wallet'
import { FundingError, TransactionError, type ChainGateway, type Hex, type TransactionReceipt } from './submitJob'

const erc20Abi = [
  { type: 'function', name: 'allowance', stateMutability: 'view', inputs: [{ name: 'owner', type: 'address' }, { name: 'spender', type: 'address' }], outputs: [{ type: 'uint256' }] },
  { type: 'function', name: 'balanceOf', stateMutability: 'view', inputs: [{ name: 'account', type: 'address' }], outputs: [{ type: 'uint256' }] },
  { type: 'function', name: 'approve', stateMutability: 'nonpayable', inputs: [{ name: 'spender', type: 'address' }, { name: 'amount', type: 'uint256' }], outputs: [{ type: 'bool' }] },
] as const

export function isDefinitivelyDropped(transactionFound: boolean, pendingNonce: number, submittedNonce: number): boolean {
  return !transactionFound && pendingNonce <= submittedNonce
}

/**
 * Build a fresh EIP-1559 fee cap immediately before broadcasting. MetaMask's
 * cached fee suggestion can be a few milliseconds behind Arbitrum's current
 * base fee, which causes `max fee per gas less than block base fee` before the
 * transaction ever reaches the contract.
 */
async function currentFeeOverrides(publicClient: ReturnType<typeof createPublicClient>) {
  const block = await publicClient.getBlock()
  const baseFee = block.baseFeePerGas ?? await publicClient.getGasPrice()
  const priority = 100_000n // 0.0001 gwei; Arbitrum's sequencer needs no tip premium.
  return {
    maxPriorityFeePerGas: priority,
    maxFeePerGas: baseFee * 2n + priority,
  }
}

function paymentAddress(): Address {
  if (!/^0x[0-9a-fA-F]{40}$/.test(CONTRACT_ADDRESS)) throw new Error('Nebula payment contract is not configured')
  return CONTRACT_ADDRESS as Address
}

async function normalizeWriteError(
  error: unknown,
  rejection: 'approval_rejected' | 'create_rejected',
  getChainId: () => Promise<number>,
): Promise<never> {
  const name = error instanceof Error ? error.name : ''
  if (/InsufficientFunds/i.test(name)) throw new FundingError('insufficient_native')
  if (/ChainMismatch|SwitchChain/i.test(name)) throw new WrongChainError(await getChainId())
  throw new TransactionError(rejection)
}

export function createInjectedChainGateway(provider: Eip1193Provider): ChainGateway {
  const transport = custom(provider)
  const publicClient = createPublicClient({ chain: arbitrumSepolia, transport })
  const walletClient = createWalletClient({ chain: arbitrumSepolia, transport })
  const address = paymentAddress()
  const abi = contractArtifact.abi as Abi
  const submittedTransactions = new Map<Hash, { account: Address; nonce: number }>()

  async function account(signal?: AbortSignal): Promise<Address> {
    signal?.throwIfAborted()
    const chainId = await walletClient.getChainId()
    if (chainId !== ARBITRUM_SEPOLIA_CHAIN_ID) throw new WrongChainError(chainId)
    const [current] = await walletClient.getAddresses()
    if (!current) throw new Error('Connect a wallet before submitting a job')
    signal?.throwIfAborted()
    return current
  }

  return {
    async inspectFunding(signal) {
      const owner = await account(signal)
      const [jobPrice, token, nativeBalance] = await Promise.all([
        publicClient.readContract({ address, abi, functionName: 'jobPrice' }) as Promise<bigint>,
        publicClient.readContract({ address, abi, functionName: 'token' }) as Promise<Address>,
        publicClient.getBalance({ address: owner }),
      ])
      const [allowance, usdcBalance] = await Promise.all([
        publicClient.readContract({ address: token, abi: erc20Abi, functionName: 'allowance', args: [owner, address] }),
        publicClient.readContract({ address: token, abi: erc20Abi, functionName: 'balanceOf', args: [owner] }),
      ])
      const gasPrice = await publicClient.getGasPrice()
      const requiredNativeBalance = gasPrice * (allowance < jobPrice ? 320_000n : 250_000n)
      signal?.throwIfAborted()
      return { account: owner, token, spender: address, jobPrice, allowance, usdcBalance, nativeBalance, requiredNativeBalance }
    },

    async approveExact(amount, signal) {
      const owner = await account(signal)
      const token = await publicClient.readContract({ address, abi, functionName: 'token' }) as Address
      const nonce = await publicClient.getTransactionCount({ address: owner, blockTag: 'pending' })
      try {
        const fee = await currentFeeOverrides(publicClient)
        const hash = await walletClient.writeContract({ account: owner, chain: arbitrumSepolia, address: token, abi: erc20Abi, functionName: 'approve', args: [address, amount], nonce, ...fee })
        submittedTransactions.set(hash, { account: owner, nonce })
        return hash
      } catch (error) {
        return normalizeWriteError(error, 'approval_rejected', () => walletClient.getChainId())
      }
    },

    async createJob(chainJobId, fingerprint, signal) {
      const owner = await account(signal)
      const nonce = await publicClient.getTransactionCount({ address: owner, blockTag: 'pending' })
      try {
        const fee = await currentFeeOverrides(publicClient)
        const hash = await walletClient.writeContract({ account: owner, chain: arbitrumSepolia, address, abi, functionName: 'createJob', args: [chainJobId, fingerprint], nonce, ...fee })
        submittedTransactions.set(hash, { account: owner, nonce })
        return hash
      } catch (error) {
        return normalizeWriteError(error, 'create_rejected', () => walletClient.getChainId())
      }
    },

    async waitForReceipt(transactionHash, signal): Promise<TransactionReceipt> {
      let replacement: TransactionReceipt['replacement']
      let cancelled = false
      const hash = transactionHash as Hash
      let receipt
      try {
        receipt = await publicClient.waitForTransactionReceipt({
          hash, confirmations: 1, timeout: 120_000,
          onReplaced: ({ reason }) => {
            if (reason === 'cancelled') cancelled = true
            else replacement = reason === 'repriced' ? 'repriced' : 'replaced'
          },
        })
      } catch (error) {
        const submitted = submittedTransactions.get(hash)
        if (submitted) {
          try {
            await publicClient.getTransaction({ hash })
          } catch (lookupError) {
            if (lookupError instanceof TransactionNotFoundError) {
              const pendingNonce = await publicClient.getTransactionCount({ address: submitted.account, blockTag: 'pending' })
              if (isDefinitivelyDropped(false, pendingNonce, submitted.nonce)) {
                submittedTransactions.delete(hash)
                return { status: 'dropped', transactionHash }
              }
            }
          }
        }
        throw error
      }
      signal?.throwIfAborted()
      submittedTransactions.delete(hash)
      if (cancelled) return { status: 'dropped', transactionHash: receipt.transactionHash as Hex }
      return {
        status: receipt.status === 'success' ? 'success' : 'reverted',
        transactionHash: receipt.transactionHash as Hex,
        replacement,
      }
    },
  }
}

/** Withdraw the connected provider's pull-payment balance from the contract. */
export async function withdrawInjectedWallet(provider: Eip1193Provider, signal?: AbortSignal): Promise<Hex> {
  const transport = custom(provider)
  const publicClient = createPublicClient({ chain: arbitrumSepolia, transport })
  const walletClient = createWalletClient({ chain: arbitrumSepolia, transport })
  const address = paymentAddress()
  const abi = contractArtifact.abi as Abi
  const [chainId, account] = await Promise.all([walletClient.getChainId(), walletClient.getAddresses()])
  if (chainId !== ARBITRUM_SEPOLIA_CHAIN_ID) throw new WrongChainError(chainId)
  const owner = account[0]
  if (!owner) throw new Error('Connect the provider wallet before withdrawing')
  signal?.throwIfAborted()
  const nonce = await publicClient.getTransactionCount({ address: owner, blockTag: 'pending' })
  const fee = await currentFeeOverrides(publicClient)
  const hash = await walletClient.writeContract({ account: owner, chain: arbitrumSepolia, address, abi, functionName: 'withdraw', nonce, ...fee })
  const receipt = await publicClient.waitForTransactionReceipt({ hash, confirmations: 1, timeout: 120_000 })
  if (receipt.status !== 'success') throw new Error('Withdrawal transaction reverted')
  return hash as Hex
}
