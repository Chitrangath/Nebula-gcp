// SPDX-License-Identifier: MIT
pragma solidity 0.8.20;

import {Deploy} from "./Deploy.s.sol";
import {DeploymentConfig} from "./DeploymentConfig.sol";
import {LocalMockUSDC} from "./LocalMockUSDC.sol";
import {NebulaVerifiableAI} from "../src/NebulaVerifiableAI.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";

/// @title Smoke
/// @notice Runs the bounded Nebula settlement rehearsal on local Anvil only.
/// @dev Uses unlocked deterministic Anvil accounts; it does not read or handle private keys.
contract Smoke is Deploy {
    uint256 internal constant LOCAL_CHAIN_ID = 31_337;
    uint256 internal constant JOB_PRICE = 50_000;
    uint256 internal constant MAX_JOB_AMOUNT = 10_000_000;

    struct SmokeIdentities {
        address deployer;
        address owner;
        address verifier;
        address aiUser;
        address provider;
        address workerSigner;
    }

    struct SmokeResult {
        NebulaVerifiableAI payment;
        LocalMockUSDC usdc;
        uint256 jobPrice;
        uint256 providerBalance;
        uint256 aiUserBalance;
        uint256 contractBalance;
    }

    error InvalidSmokeIdentity();
    error DuplicateSmokeIdentity();
    error SmokeAssertionFailed(bytes32 assertionName);

    /// @notice Execute the complete local rehearsal using explicitly named unlocked Anvil accounts.
    function run() external override returns (NebulaVerifiableAI payment) {
        SmokeResult memory result = _runLocalSmoke(_loadSmokeIdentities());
        return result.payment;
    }

    function _loadSmokeIdentities() private view returns (SmokeIdentities memory) {
        return SmokeIdentities({
            deployer: vm.envAddress("ANVIL_DEPLOYER_ADDRESS"),
            owner: vm.envAddress("ANVIL_OWNER_ADDRESS"),
            verifier: vm.envAddress("ANVIL_VERIFIER_ADDRESS"),
            aiUser: vm.envAddress("ANVIL_AI_USER_ADDRESS"),
            provider: vm.envAddress("ANVIL_PROVIDER_ADDRESS"),
            workerSigner: vm.envAddress("ANVIL_WORKER_SIGNER_ADDRESS")
        });
    }

    function _runLocalSmoke(
        SmokeIdentities memory configuredIdentities
    ) internal returns (SmokeResult memory result) {
        address[6] memory identities = _validateIdentities(configuredIdentities);
        if (block.chainid != LOCAL_CHAIN_ID) {
            revert DeploymentConfig.UnexpectedChain(block.chainid, LOCAL_CHAIN_ID);
        }
        address deployer = identities[0];
        address owner = identities[1];
        address verifier = identities[2];
        address aiUser = identities[3];
        address provider = identities[4];

        vm.startBroadcast(deployer);
        LocalMockUSDC usdc = new LocalMockUSDC(deployer);
        vm.stopBroadcast();

        DeploymentConfig.Values memory values = DeploymentConfig.Values({
            network: DeploymentConfig.NetworkMode.Local,
            usdc: address(usdc),
            owner: owner,
            verifier: verifier,
            jobPrice: JOB_PRICE,
            maxJobAmount: MAX_JOB_AMOUNT
        });
        DeploymentConfig.validate(values);
        NebulaVerifiableAI payment = _broadcastValidatedFrom(values, deployer);

        vm.startBroadcast(deployer);
        usdc.mint(aiUser, JOB_PRICE * 2);
        vm.stopBroadcast();

        bytes32 validJobId = bytes32(uint256(1) << 128);
        bytes32 invalidJobId = bytes32(uint256(2) << 128);
        bytes32 pausedJobId = bytes32(uint256(3) << 128);
        bytes32 validLeaseId = keccak256("nebula-local-valid-lease");
        bytes32 invalidLeaseId = keccak256("nebula-local-invalid-lease");
        bytes32 fingerprint = keccak256("nebula-local-fingerprint");

        vm.startBroadcast(aiUser);
        usdc.approve(address(payment), JOB_PRICE * 2);
        payment.createJob(validJobId, fingerprint);
        vm.stopBroadcast();
        _assertSolvent(payment);

        _assertUnauthorizedAssignment(payment, aiUser, validJobId, provider, validLeaseId);
        _assertPauseBehavior(payment, owner, aiUser, pausedJobId, fingerprint);

        vm.startBroadcast(verifier);
        payment.assignProvider(validJobId, provider, validLeaseId, uint64(block.timestamp + 1 hours));
        payment.submitProof(validJobId, validLeaseId, keccak256("valid-merkle-root"), keccak256("valid-output"));
        vm.stopBroadcast();
        _assertUnauthorizedSettlement(payment, aiUser, validJobId);

        vm.startBroadcast(verifier);
        payment.verifyJob(validJobId, true);
        vm.stopBroadcast();
        _assertCredit(payment, provider);
        _assertSolvent(payment);
        _assertDuplicateSettlement(payment, verifier, validJobId);

        vm.startBroadcast(provider);
        payment.withdraw();
        vm.stopBroadcast();
        _assertSolvent(payment);

        vm.startBroadcast(aiUser);
        payment.createJob(invalidJobId, fingerprint);
        vm.stopBroadcast();

        vm.startBroadcast(verifier);
        payment.assignProvider(invalidJobId, provider, invalidLeaseId, uint64(block.timestamp + 1 hours));
        payment.submitProof(invalidJobId, invalidLeaseId, keccak256("invalid-merkle-root"), keccak256("invalid-output"));
        payment.verifyJob(invalidJobId, false);
        vm.stopBroadcast();
        _assertCredit(payment, aiUser);
        _assertSolvent(payment);

        vm.startBroadcast(aiUser);
        payment.withdraw();
        vm.stopBroadcast();

        result = SmokeResult({
            payment: payment,
            usdc: usdc,
            jobPrice: JOB_PRICE,
            providerBalance: usdc.balanceOf(provider),
            aiUserBalance: usdc.balanceOf(aiUser),
            contractBalance: usdc.balanceOf(address(payment))
        });
        _assertFinalState(result);
    }

    function _validateIdentities(
        SmokeIdentities memory configuredIdentities
    ) private pure returns (address[6] memory identities) {
        identities = [
            configuredIdentities.deployer,
            configuredIdentities.owner,
            configuredIdentities.verifier,
            configuredIdentities.aiUser,
            configuredIdentities.provider,
            configuredIdentities.workerSigner
        ];

        for (uint256 i; i < identities.length; ++i) {
            if (identities[i] == address(0)) revert InvalidSmokeIdentity();
            for (uint256 j; j < i; ++j) {
                if (identities[i] == identities[j]) revert DuplicateSmokeIdentity();
            }
        }
    }

    function _assertUnauthorizedAssignment(
        NebulaVerifiableAI payment,
        address aiUser,
        bytes32 jobId,
        address provider,
        bytes32 leaseId
    ) private {
        vm.prank(aiUser);
        vm.expectRevert(NebulaVerifiableAI.OnlyVerifier.selector);
        payment.assignProvider(jobId, provider, leaseId, uint64(block.timestamp + 1 hours));
    }

    function _assertPauseBehavior(
        NebulaVerifiableAI payment,
        address owner,
        address aiUser,
        bytes32 jobId,
        bytes32 fingerprint
    ) private {
        vm.startBroadcast(owner);
        payment.pause();
        vm.stopBroadcast();

        vm.prank(aiUser);
        vm.expectRevert(Pausable.EnforcedPause.selector);
        payment.createJob(jobId, fingerprint);

        vm.startBroadcast(owner);
        payment.unpause();
        vm.stopBroadcast();
    }

    function _assertUnauthorizedSettlement(
        NebulaVerifiableAI payment,
        address aiUser,
        bytes32 jobId
    ) private {
        vm.prank(aiUser);
        vm.expectRevert(NebulaVerifiableAI.OnlyVerifier.selector);
        payment.verifyJob(jobId, true);
    }

    function _assertDuplicateSettlement(
        NebulaVerifiableAI payment,
        address verifier,
        bytes32 jobId
    ) private {
        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.NoProofSubmitted.selector);
        payment.verifyJob(jobId, true);
    }

    function _assertSolvent(
        NebulaVerifiableAI payment
    ) private view {
        if (!payment.invariant_solvency()) revert SmokeAssertionFailed("SOLVENCY");
    }

    function _assertCredit(
        NebulaVerifiableAI payment,
        address recipient
    ) private view {
        if (payment.pendingWithdrawals(recipient) != JOB_PRICE) {
            revert SmokeAssertionFailed("PENDING_RECIPIENT");
        }
        if (payment.totalPendingWithdrawals() != JOB_PRICE) {
            revert SmokeAssertionFailed("TOTAL_PENDING");
        }
    }

    function _assertFinalState(
        SmokeResult memory result
    ) private view {
        if (result.providerBalance != JOB_PRICE) revert SmokeAssertionFailed("PROVIDER_BALANCE");
        if (result.aiUserBalance != JOB_PRICE) revert SmokeAssertionFailed("USER_BALANCE");
        if (result.contractBalance != 0) revert SmokeAssertionFailed("CONTRACT_BALANCE");
        if (result.payment.totalEscrowed() != 0) revert SmokeAssertionFailed("TOTAL_ESCROWED");
        if (result.payment.totalPendingWithdrawals() != 0) revert SmokeAssertionFailed("TOTAL_PENDING");
        _assertSolvent(result.payment);
    }
}
