// SPDX-License-Identifier: MIT
pragma solidity 0.8.20;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {SafeCast} from "@openzeppelin/contracts/utils/math/SafeCast.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";

/// @title NebulaVerifiableAI
/// @notice Verifiable AI execution with Proof-of-AI-Execution (PoAE)
/// @dev Job IDs are UUIDs left-aligned in bytes32 (16 raw bytes + 16 zero bytes). Uses SafeERC20 for safe token transfers.
/// @notice Trust assumptions:
///   - Owner is trusted (can pause, set verifier, set job price) — production should use multisig/timelock
///   - Verifier is trusted (can submit proofs and settle jobs as valid/invalid)
///   - Provider is assigned by backend; proof binding enforced on-chain
/// @custom:security A job can only be settled once. USDC is conserved (no create/destroy).
///   Pull payments via pendingWithdrawals + withdraw() with CEI pattern.
///   Solvency: usdc.balanceOf(this) >= totalEscrowed + totalPendingWithdrawals
///   (both active escrow and credited-but-unwithdrawn balances are simultaneous contract liabilities).
/// @custom:timestamp Relies on Arbitrum's minimum block timestamp (parent +1s) and
///   maximum timestamp (parent +12s) rules. One-hour leases and 24-hour deadlines provide
///   a safety margin far exceeding any plausible timestamp drift.
contract NebulaVerifiableAI is Ownable, ReentrancyGuard, Pausable {
    using SafeERC20 for IERC20;

    // ──────────────────────────────────────────────
    // Enums
    // ──────────────────────────────────────────────

    enum JobState {
        None,
        Created,
        Assigned,
        ProofSubmitted,
        Settled,
        Refunded
    }

    // ──────────────────────────────────────────────
    // Errors
    // ──────────────────────────────────────────────

    error InvalidUSDC();
    error InvalidVerifier();
    error InvalidProvider();
    error InvalidLeaseID();
    error InvalidAmount();
    error InvalidJobID();
    error InvalidFingerprint();
    error InvalidMerkleRoot();
    error InvalidOutputHash();
    error JobAlreadyExists();
    error JobNotFound();
    error JobNotInState();
    error NotJobCreator();
    error NotAssignedProvider();
    error OnlyVerifier();
    error LeaseExpired();
    error LeaseMismatch();
    error JobDeadlineExpired();
    error ProofAlreadySubmitted();
    error NoProofSubmitted();
    error AmountExceedsMax();
    error InvalidJobPrice();
    error RefundTooEarly();
    error RefundAlreadyProcessed();
    error WithdrawInsufficient();

    // ──────────────────────────────────────────────
    // Events
    // ──────────────────────────────────────────────

    event VerifierUpdated(address indexed oldVerifier, address indexed newVerifier);
    event MaxJobAmountUpdated(uint256 oldMax, uint256 newMax);
    event JobPriceUpdated(uint256 oldPrice, uint256 newPrice);
    event JobCreated(
        bytes32 indexed jobId, address indexed user, bytes32 fingerprint, uint256 amount, uint256 timestamp
    );
    event ProviderAssigned(bytes32 indexed jobId, address indexed provider, bytes32 leaseId, uint64 leaseExpiresAt);
    event ProofSubmitted(
        bytes32 indexed jobId, bytes32 leaseId, bytes32 merkleRoot, bytes32 outputHash, address provider
    );
    event JobSettled(bytes32 indexed jobId, bool valid, uint256 timestamp);
    event PaymentCredited(bytes32 indexed jobId, address indexed provider, uint256 amount);
    event WithdrawalCompleted(address indexed provider, uint256 amount);
    event TimeoutRefundCredited(bytes32 indexed jobId, address indexed user, uint256 amount);

    // ──────────────────────────────────────────────
    // Structs & Storage
    // ──────────────────────────────────────────────

    /// @dev Packed layout: 9 storage slots. Removed redundant jobId (key).
    ///   Timestamps shrunk from uint256 to uint64; packed with state.
    struct Job {
        address user; // slot 0: 20 bytes
        address provider; // slot 1: 20 bytes
        bytes32 fingerprint; // slot 2: 32 bytes
        bytes32 merkleRoot; // slot 3: 32 bytes
        bytes32 outputHash; // slot 4: 32 bytes
        bytes32 leaseId; // slot 5: 32 bytes
        uint256 amount; // slot 6: 32 bytes
        uint64 leaseExpiresAt; // slot 7: 8 bytes
        uint64 jobDeadline; // slot 7: 8 bytes
        uint64 createdAt; // slot 7: 8 bytes
        uint64 completedAt; // slot 7: 8 bytes
        JobState state; // slot 8: 1 byte
    }

    IERC20 public immutable usdc;
    address public verifier;
    uint256 public maxJobAmount;
    uint256 public jobPrice;

    mapping(bytes32 => Job) public jobs;
    mapping(address => uint256) public pendingWithdrawals;
    uint256 public totalEscrowed; // current active escrow (decremented on settle/refund)
    uint256 public totalPendingWithdrawals;

    uint256 public constant JOB_DEADLINE_SECONDS = 86400; // 24 hours
    uint64 public constant LEASE_DURATION_SECONDS = 3600; // 1 hour

    // ──────────────────────────────────────────────
    // Modifiers
    // ──────────────────────────────────────────────

    modifier onlyVerifier() {
        if (msg.sender != verifier) revert OnlyVerifier();
        _;
    }

    // ──────────────────────────────────────────────
    // Constructor
    // ──────────────────────────────────────────────

    constructor(
        address _usdc
    ) Ownable(msg.sender) {
        if (_usdc == address(0)) revert InvalidUSDC();
        usdc = IERC20(_usdc);
        verifier = msg.sender;
        maxJobAmount = 10e6; // 10 USDC default cap (6 decimals)
        jobPrice = 50_000; // 0.05 USDC default price (50,000 base units)
    }

    // ──────────────────────────────────────────────
    // Admin
    // ──────────────────────────────────────────────

    /// @notice Reassign the verifier role
    function setVerifier(
        address _verifier
    ) external onlyOwner {
        if (_verifier == address(0)) revert InvalidVerifier();
        address old = verifier;
        verifier = _verifier;
        emit VerifierUpdated(old, _verifier);
    }

    /// @notice Update the maximum escrow amount per job. Must be >= jobPrice.
    function setMaxJobAmount(
        uint256 _max
    ) external onlyOwner {
        if (_max < jobPrice) revert AmountExceedsMax();
        uint256 old = maxJobAmount;
        maxJobAmount = _max;
        emit MaxJobAmountUpdated(old, _max);
    }

    /// @notice Update the job price. Must be > 0 and <= maxJobAmount.
    function setJobPrice(
        uint256 _price
    ) external onlyOwner {
        if (_price == 0 || _price > maxJobAmount) revert InvalidJobPrice();
        uint256 old = jobPrice;
        jobPrice = _price;
        emit JobPriceUpdated(old, _price);
    }

    /// @notice Pause or unpause the contract. Only owner.
    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }

    // ──────────────────────────────────────────────
    // Core — Job Lifecycle
    // ──────────────────────────────────────────────

    /// @notice Create a new job, escrow exactly jobPrice USDC. User-funded via MetaMask.
    /// @param chainJobId UUID left-aligned in bytes32 (16 raw bytes + 16 zero bytes)
    /// @param fingerprint Deterministic hash of model+input+metadata
    /// @return jobId The chainJobId passed through (bytes32)
    function createJob(
        bytes32 chainJobId,
        bytes32 fingerprint
    ) external whenNotPaused returns (bytes32 jobId) {
        if (chainJobId == bytes32(0)) revert InvalidJobID();
        if (uint128(uint256(chainJobId)) != 0) revert InvalidJobID();
        if (fingerprint == bytes32(0)) revert InvalidFingerprint();

        jobId = chainJobId;
        if (jobs[jobId].user != address(0)) revert JobAlreadyExists();

        uint256 amount = jobPrice;

        // Pull USDC from user
        usdc.safeTransferFrom(msg.sender, address(this), amount);

        uint64 deadline = SafeCast.toUint64(block.timestamp + JOB_DEADLINE_SECONDS);
        jobs[jobId] = Job({
            user: msg.sender,
            provider: address(0),
            fingerprint: fingerprint,
            merkleRoot: bytes32(0),
            outputHash: bytes32(0),
            leaseId: bytes32(0),
            amount: amount,
            leaseExpiresAt: 0,
            jobDeadline: deadline,
            createdAt: SafeCast.toUint64(block.timestamp),
            completedAt: 0,
            state: JobState.Created
        });

        totalEscrowed += amount;

        emit JobCreated(jobId, msg.sender, fingerprint, amount, block.timestamp);
    }

    /// @notice Assign a provider to a job. Can be initial (Created→Assigned) or reassignment (Assigned→Assigned).
    /// @dev Validation precedence (order is guaranteed even under IR optimization):
    ///   1. Existence  2. State  3. Deadline  4. Old-lease expiry (reassignment)  5. New lease validity
    function assignProvider(
        bytes32 jobId,
        address provider,
        bytes32 leaseId,
        uint64 leaseExpiresAt
    ) external onlyVerifier whenNotPaused {
        // ── 1. Input validation ──
        if (provider == address(0)) revert InvalidProvider();
        if (leaseId == bytes32(0)) revert InvalidLeaseID();

        // ── 2. Existence ──
        Job storage job = jobs[jobId];
        if (job.user == address(0)) revert JobNotFound();

        // ── 3. State ──
        JobState state = job.state;
        if (state != JobState.Created && state != JobState.Assigned) revert JobNotInState();

        // ── 4. Job deadline (canonical — checked before any lease logic) ──
        if (block.timestamp > job.jobDeadline) revert JobDeadlineExpired();

        // ── 5. Reassignment guards (old lease must be strictly expired) ──
        if (state == JobState.Assigned) {
            if (block.timestamp <= job.leaseExpiresAt) revert LeaseExpired();
            if (leaseId == job.leaseId) revert LeaseMismatch();
        }

        // ── 6. New lease validity: now < newExpiry ≤ deadline ──
        if (leaseExpiresAt <= block.timestamp) revert LeaseExpired();
        if (leaseExpiresAt > job.jobDeadline) revert JobDeadlineExpired();

        // ── 7. Apply ──
        job.provider = provider;
        job.leaseId = leaseId;
        job.leaseExpiresAt = leaseExpiresAt;
        if (state == JobState.Created) {
            job.state = JobState.Assigned;
        }

        emit ProviderAssigned(jobId, provider, leaseId, leaseExpiresAt);
    }

    /// @notice Submit PoAE proof for a job. Only callable by verifier.
    /// @dev Validates leaseId match, lease not expired, deadline not expired.
    function submitProof(
        bytes32 jobId,
        bytes32 leaseId,
        bytes32 merkleRoot,
        bytes32 outputHash
    ) external onlyVerifier whenNotPaused {
        if (merkleRoot == bytes32(0)) revert InvalidMerkleRoot();
        if (outputHash == bytes32(0)) revert InvalidOutputHash();

        Job storage job = jobs[jobId];
        if (job.user == address(0)) revert JobNotFound();
        if (job.state != JobState.Assigned) revert JobNotInState();
        if (leaseId != job.leaseId) revert LeaseMismatch();
        if (block.timestamp > job.leaseExpiresAt) revert LeaseExpired();
        if (block.timestamp > job.jobDeadline) revert JobDeadlineExpired();

        job.merkleRoot = merkleRoot;
        job.outputHash = outputHash;
        job.state = JobState.ProofSubmitted;

        emit ProofSubmitted(jobId, leaseId, merkleRoot, outputHash, job.provider);
    }

    /// @notice Verify a job and settle payment. Only callable by verifier.
    /// @dev ReentrancyGuard protects the external USDC transfer via pull payment.
    function verifyJob(
        bytes32 jobId,
        bool isValid
    ) external onlyVerifier nonReentrant {
        Job storage job = jobs[jobId];
        if (job.user == address(0)) revert JobNotFound();
        if (job.state != JobState.ProofSubmitted) revert NoProofSubmitted();

        // Cache storage reads to avoid redundant SLOADs
        uint256 jobAmount = job.amount;
        address jobProvider = job.provider;
        address jobUser = job.user;

        // Effects before interactions (CEI)
        job.completedAt = SafeCast.toUint64(block.timestamp);
        job.state = isValid ? JobState.Settled : JobState.Refunded;

        // Transfer from escrow to pending (decrement escrow, increment pending)
        totalEscrowed -= jobAmount;

        if (isValid) {
            // Credit provider via pull payment
            pendingWithdrawals[jobProvider] += jobAmount;
            totalPendingWithdrawals += jobAmount;
            emit PaymentCredited(jobId, jobProvider, jobAmount);
        } else {
            // Credit user via pull payment
            pendingWithdrawals[jobUser] += jobAmount;
            totalPendingWithdrawals += jobAmount;
            emit TimeoutRefundCredited(jobId, jobUser, jobAmount);
        }

        emit JobSettled(jobId, isValid, block.timestamp);
    }

    /// @notice Request timeout refund. Only callable by job creator, only after jobDeadline.
    /// @dev Allowed from Created, Assigned, and ProofSubmitted states so that a user can
    ///   recover escrow even if the verifier submitted a proof but never settles it.
    ///   Terminal states (Settled, Refunded) reject.
    function requestTimeoutRefund(
        bytes32 jobId
    ) external nonReentrant {
        Job storage job = jobs[jobId];
        if (job.user == address(0)) revert JobNotFound();
        if (msg.sender != job.user) revert NotJobCreator();
        if (block.timestamp <= job.jobDeadline) revert RefundTooEarly();

        JobState state = job.state;

        // Allow refund from Created, Assigned, or ProofSubmitted states (pre-settlement).
        if (state != JobState.Created && state != JobState.Assigned && state != JobState.ProofSubmitted) {
            revert RefundAlreadyProcessed();
        }

        // Cache storage reads
        uint256 jobAmount = job.amount;
        address jobUser = job.user;

        // Transfer from escrow to pending (decrement escrow, increment pending)
        totalEscrowed -= jobAmount;

        // Credit user via pull payment
        pendingWithdrawals[jobUser] += jobAmount;
        totalPendingWithdrawals += jobAmount;
        job.state = JobState.Refunded;
        job.completedAt = SafeCast.toUint64(block.timestamp);

        emit TimeoutRefundCredited(jobId, jobUser, jobAmount);
    }

    // ──────────────────────────────────────────────
    // Withdrawals (Pull Payment)
    // ──────────────────────────────────────────────

    /// @notice Withdraw accumulated earnings/refunds. CEI pattern, nonReentrant.
    function withdraw() external nonReentrant {
        uint256 amount = pendingWithdrawals[msg.sender];
        if (amount == 0) revert WithdrawInsufficient();

        // Effects before interactions
        pendingWithdrawals[msg.sender] = 0;
        totalPendingWithdrawals -= amount;

        // Interaction (SafeERC20 handles non-standard/no-return/reverting tokens)
        usdc.safeTransfer(msg.sender, amount);

        emit WithdrawalCompleted(msg.sender, amount);
    }

    // ──────────────────────────────────────────────
    // View Helpers
    // ──────────────────────────────────────────────

    /// @notice Get job details (returns individual fields to avoid string copy gas cost)
    function getJob(
        bytes32 jobId
    )
        external
        view
        returns (
            address user,
            address provider,
            bytes32 fingerprint,
            bytes32 merkleRoot,
            bytes32 outputHash,
            bytes32 leaseId,
            uint256 amount,
            uint64 leaseExpiresAt,
            uint64 jobDeadline,
            uint64 createdAt,
            uint64 completedAt,
            JobState state
        )
    {
        Job storage job = jobs[jobId];
        return (
            job.user,
            job.provider,
            job.fingerprint,
            job.merkleRoot,
            job.outputHash,
            job.leaseId,
            job.amount,
            job.leaseExpiresAt,
            job.jobDeadline,
            job.createdAt,
            job.completedAt,
            job.state
        );
    }

    /// @notice Get pending withdrawal amount for an address
    function getPendingWithdrawal(
        address account
    ) external view returns (uint256) {
        return pendingWithdrawals[account];
    }

    /// @notice Read the immutable USDC token address
    function token() external view returns (address) {
        return address(usdc);
    }

    // ──────────────────────────────────────────────
    // Invariant Checks (view functions for verification)
    // ──────────────────────────────────────────────

    /// @notice Solvency invariant: contract must hold enough USDC to cover
    ///   both active escrow (jobs in Created/Assigned state) and
    ///   credited-but-unwithdrawn balances (settled/refunded jobs awaiting withdraw).
    ///   Both are simultaneous contract liabilities.
    function invariant_solvency() external view returns (bool) {
        return usdc.balanceOf(address(this)) >= totalEscrowed + totalPendingWithdrawals;
    }

    /// @notice No-double-settle invariant: cannot settle a job twice
    /// @dev Enforced by state machine: ProofSubmitted -> Settled/Refunded only
    function invariant_no_double_settle(
        bytes32 jobId
    ) external view returns (bool) {
        Job memory job = jobs[jobId];
        if (job.state != JobState.Settled && job.state != JobState.Refunded) return true;
        return job.completedAt > 0;
    }
}
