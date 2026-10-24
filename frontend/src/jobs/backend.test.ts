import { afterEach, describe, expect, it, vi } from 'vitest'

import { getJobResult, jobBackend, listSupportedModels, probabilityFromHexFloat } from './backend'
import { clearAccessToken, enableSessionRefresh, setAccessToken } from '../api/session'

describe('job backend client', () => {
  afterEach(() => vi.restoreAllMocks())

  it('uploads multipart input with one idempotency key and normalizes the fingerprint', async () => {
    clearAccessToken(); enableSessionRefresh(); setAccessToken('access')
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      id: 'job-id', chain_job_id: `0x${'12'.repeat(32)}`, fingerprint: '34'.repeat(32), price_base_units: '50000',
      model_id: 'resnet50', status: 'pending_blockchain', deadline: '2099-01-01T00:00:00Z', created_at: '2026-01-01T00:00:00Z',
      attempt_count: 0, result_available: false, reconciliation_health: 'pending',
    }), { status: 200 }))

    const job = await jobBackend.createJob({ modelId: 'resnet50', input: new File(['png'], 'input.png', { type: 'image/png' }), deadline: '2099-01-01T00:00:00Z' }, 'one-key')

    const init = fetchMock.mock.calls[0][1]
    expect(init?.body).toBeInstanceOf(FormData)
    expect(new Headers(init?.headers).get('Content-Type')).toBeNull()
    expect(new Headers(init?.headers).get('Idempotency-Key')).toBe('one-key')
    expect(job.fingerprint).toBe(`0x${'34'.repeat(32)}`)
  })

  it('sends only the transaction hash when confirming escrow', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ id: 'job-id', status: 'escrow_confirmed', blockchain_tx_hash: `0x${'ab'.repeat(32)}`, blockchain_escrow_amount: '50000' }), { status: 200 }))

    await jobBackend.confirmEscrow('job-id', `0x${'ab'.repeat(32)}`)

    const body = vi.mocked(fetch).mock.calls[0][1]?.body
    expect(JSON.parse(String(body))).toEqual({ tx_hash: `0x${'ab'.repeat(32)}` })
  })

  it.each([
    [{ id: 'resnet50', name: 'R', input_type: 'image', supported_formats: [42], price_base_units: '50000' }],
    [{ id: 'resnet50', name: 'R', input_type: 'image', supported_formats: ['png'], max_input_size_mb: -1, price_base_units: '50000' }],
  ])('rejects malformed model metadata at the API boundary', async (malformed) => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify([malformed]), { status: 200 }))
    await expect(listSupportedModels()).rejects.toThrow('Invalid model response')
  })

  it('parses a canonical BERT result without interpreting untrusted fields', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      model_id: 'bert-base', stars: 5, scores: [{ stars: 5, probability_hex: '0x1.0p-1' }], ignored: '<script>',
    }), { status: 200 }))

    await expect(getJobResult('job-id')).resolves.toEqual({
      model_id: 'bert-base', stars: 5, scores: [{ stars: 5, probability_hex: '0x1.0p-1' }],
    })
    expect(probabilityFromHexFloat('0x1.0p-1')).toBe(0.5)
    expect(probabilityFromHexFloat('not-a-number')).toBeNull()
  })
})
