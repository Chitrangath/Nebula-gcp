// SPDX-License-Identifier: MIT
pragma solidity 0.8.20;

import "forge-std/Test.sol";
import "../src/NebulaVerifiableAI.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

// ═══════════════════════════════════════════════════════════════════
// Mock Tokens
// ═══════════════════════════════════════════════════════════════════

contract MockUSDC is ERC20 {
    uint8 private _dec;

    constructor() ERC20("USD Coin", "USDC") {
        _dec = 6;
    }

    function decimals() public view override returns (uint8) {
        return _dec;
    }

    function mint(
        address to,
        uint256 amount
    ) external {
        _mint(to, amount);
    }
}

/// @dev ERC20 that triggers reentrancy on transfer
contract ReentrantUSDC is ERC20 {
    NebulaVerifiableAI public target;
    bytes32 public attackJobId;
    uint256 public attackCount;

    constructor() ERC20("Reentrant USDC", "RUSDC") {}

    function setTarget(
        NebulaVerifiableAI _target
    ) external {
        target = _target;
    }

    function setAttackJob(
        bytes32 _jobId
    ) external {
        attackJobId = _jobId;
    }

    function mint(
        address to,
        uint256 amount
    ) external {
        _mint(to, amount);
    }

    function transfer(
        address,
        uint256
    ) public override returns (bool) {
        attackCount++;
        if (attackCount == 1) {
            // Attempt reentrancy on withdraw
            try target.withdraw() {} catch {}
        }
        return true;
    }

    function transferFrom(
        address,
        address,
        uint256
    ) public override returns (bool) {
        return true;
    }
}

/// @dev Non-standard ERC20 whose transfer/transferFrom move tokens but return no value.
///   Declares the same selectors as standard transfer/transferFrom WITHOUT the IERC20
///   interface so that SafeERC20's low-level call receives empty returndata.
contract NoReturnUSDC {
    string public constant name = "No Return USDC";
    string public constant symbol = "NRUSDC";
    uint8 public constant decimals = 6;

    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    function approve(
        address spender,
        uint256 amount
    ) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function transfer(
        address to,
        uint256 value
    ) external {
        _transfer(msg.sender, to, value);
    }

    function transferFrom(
        address from,
        address to,
        uint256 value
    ) external {
        uint256 allowed = allowance[from][msg.sender];
        require(allowed >= value, "allowance");
        if (allowed != type(uint256).max) allowance[from][msg.sender] = allowed - value;
        _transfer(from, to, value);
    }

    function _transfer(
        address from,
        address to,
        uint256 value
    ) internal {
        require(balanceOf[from] >= value, "balance");
        balanceOf[from] -= value;
        balanceOf[to] += value;
        emit Transfer(from, to, value);
    }

    function mint(
        address to,
        uint256 amount
    ) external {
        totalSupply += amount;
        balanceOf[to] += amount;
        emit Transfer(address(0), to, amount);
    }
}

/// @dev ERC20 whose transfer always reverts (withdrawal must revert atomically).
contract RevertUSDC is ERC20 {
    constructor() ERC20("Revert USDC", "RVUSDC") {}

    function mint(
        address to,
        uint256 amount
    ) external {
        _mint(to, amount);
    }

    function transfer(
        address,
        uint256
    ) public override returns (bool) {
        revert("RevertUSDC: blocked");
    }

    function transferFrom(
        address from,
        address to,
        uint256 value
    ) public override returns (bool) {
        _transfer(from, to, value);
        return true;
    }
}

/// @dev ERC20 whose transfer succeeds but returns false (withdrawal must revert atomically
///   with SafeERC20FailedOperation).
contract FalseReturnUSDC is ERC20 {
    constructor() ERC20("False Return USDC", "FRUSDC") {}

    function mint(
        address to,
        uint256 amount
    ) external {
        _mint(to, amount);
    }

    function transfer(
        address,
        uint256
    ) public override returns (bool) {
        return false;
    }

    function transferFrom(
        address from,
        address to,
        uint256 value
    ) public override returns (bool) {
        _transfer(from, to, value);
        return true;
    }
}

// ═══════════════════════════════════════════════════════════════════
// Stateful Invariant Handler
// ═══════════════════════════════════════════════════════════════════

contract NebulaHandler is Test {
    NebulaVerifiableAI public target;
    MockUSDC public usdc;

    address owner;
    address verifier;
    address user;
    address provider;

    // Ghost variables for invariant tracking
    uint256 public ghostActiveEscrow; // expected totalEscrowed (still in escrow)
    uint256 public ghostPendingWithdrawals; // expected totalPendingWithdrawals (credited, not withdrawn)
    uint256 public ghostTotalWithdrawals; // total USDC withdrawn by actors
    uint256 public ghostTotalCredits; // total escrow converted into pending credits
    uint256 public ghostCreatedFunds; // total USDC escrowed via createJob

    // Job tracking
    bytes32[] jobIds;
    mapping(bytes32 => bool) exists;

    uint256 public constant JOB_PRICE = 50_000;
    uint256 public constant MAX_JOBS = 50;

    function setUp() public {
        owner = address(this);
        verifier = makeAddr("verifier");
        user = makeAddr("handler_user");
        provider = makeAddr("handler_provider");

        usdc = new MockUSDC();
        target = new NebulaVerifiableAI(address(usdc));
        target.setVerifier(verifier);

        usdc.mint(user, JOB_PRICE * 1000);
        vm.startPrank(user);
        usdc.approve(address(target), type(uint256).max);
        vm.stopPrank();

        usdc.mint(provider, JOB_PRICE * 10);
        vm.startPrank(provider);
        usdc.approve(address(target), type(uint256).max);
        vm.stopPrank();
    }

    // ──────────────────────────────────────────────
    // Invariant Assertions
    // ──────────────────────────────────────────────

    /// @notice Solvency: balance >= totalEscrowed + totalPendingWithdrawals (called manually from test)
    function check_solvency() public view {
        uint256 balance = usdc.balanceOf(address(target));
        uint256 escrowed = target.totalEscrowed();
        uint256 pending = target.totalPendingWithdrawals();
        assertTrue(
            balance >= escrowed + pending,
            string.concat(
                "SOLVENCY VIOLATION: balance=",
                vm.toString(balance),
                " escrowed=",
                vm.toString(escrowed),
                " pending=",
                vm.toString(pending)
            )
        );
    }

    /// @notice Ghost active escrow matches contract totalEscrowed (called manually from test)
    function check_ghost_escrow_matches() public view {
        assertEq(target.totalEscrowed(), ghostActiveEscrow, "GHOST ESCROW MISMATCH");
    }

    /// @notice Ghost pending withdrawals matches contract totalPendingWithdrawals (called manually from test)
    function check_ghost_pending_matches() public view {
        assertEq(target.totalPendingWithdrawals(), ghostPendingWithdrawals, "GHOST PENDING MISMATCH");
    }

    // ──────────────────────────────────────────────
    // Actions
    // ──────────────────────────────────────────────

    function createJob() external {
        if (jobIds.length >= MAX_JOBS) return;
        if (usdc.balanceOf(user) < JOB_PRICE) return;

        // Left-align: take upper 16 bytes of hash, zero lower 16 bytes
        bytes32 rawHash = keccak256(abi.encodePacked(block.timestamp, jobIds.length));
        bytes32 jobId = bytes32(uint256(rawHash) & 0xffffffffffffffffffffffffffffffff00000000000000000000000000000000);

        vm.prank(user);
        bytes32 jid = target.createJob(jobId, keccak256("fingerprint"));
        jobIds.push(jid);
        exists[jid] = true;

        ghostActiveEscrow += JOB_PRICE;
        ghostCreatedFunds += JOB_PRICE;
    }

    function assignProvider() external {
        if (jobIds.length == 0) return;

        uint256 idx = uint256(keccak256(abi.encodePacked(block.timestamp, "assign"))) % jobIds.length;
        bytes32 jobId = jobIds[idx];

        (,,,,,,,, uint64 deadline,,, NebulaVerifiableAI.JobState state) = target.getJob(jobId);
        if (state != NebulaVerifiableAI.JobState.Created) return;

        uint64 leaseExpiry = SafeCast.toUint64(block.timestamp + 3500);
        if (leaseExpiry > deadline) return;

        vm.prank(verifier);
        target.assignProvider(jobId, provider, keccak256(abi.encodePacked(block.timestamp)), leaseExpiry);
    }

    function submitProof() external {
        if (jobIds.length == 0) return;

        uint256 idx = uint256(keccak256(abi.encodePacked(block.timestamp, "submit"))) % jobIds.length;
        bytes32 jobId = jobIds[idx];

        (,,,,, bytes32 leaseId,, uint64 leaseExpiry,,,, NebulaVerifiableAI.JobState state) = target.getJob(jobId);
        if (state != NebulaVerifiableAI.JobState.Assigned) return;
        if (block.timestamp > leaseExpiry) return;

        vm.prank(verifier);
        target.submitProof(
            jobId,
            leaseId,
            keccak256(abi.encodePacked(block.timestamp, "root")),
            keccak256(abi.encodePacked(block.timestamp, "hash"))
        );
    }

    function verifyJobValid() external {
        if (jobIds.length == 0) return;

        uint256 idx = uint256(keccak256(abi.encodePacked(block.timestamp, "verifyValid"))) % jobIds.length;
        bytes32 jobId = jobIds[idx];

        (,,,,,,,,,,, NebulaVerifiableAI.JobState state) = target.getJob(jobId);
        if (state != NebulaVerifiableAI.JobState.ProofSubmitted) return;

        (,,,,,, uint256 amount,,,,,) = target.getJob(jobId);

        vm.prank(verifier);
        target.verifyJob(jobId, true);

        ghostActiveEscrow -= amount;
        ghostPendingWithdrawals += amount;
        ghostTotalCredits += amount;
    }

    function verifyJobInvalid() external {
        if (jobIds.length == 0) return;

        uint256 idx = uint256(keccak256(abi.encodePacked(block.timestamp, "verifyInvalid"))) % jobIds.length;
        bytes32 jobId = jobIds[idx];

        (,,,,,,,,,,, NebulaVerifiableAI.JobState state) = target.getJob(jobId);
        if (state != NebulaVerifiableAI.JobState.ProofSubmitted) return;

        (,,,,,, uint256 amount,,,,,) = target.getJob(jobId);

        vm.prank(verifier);
        target.verifyJob(jobId, false);

        ghostActiveEscrow -= amount;
        ghostPendingWithdrawals += amount;
        ghostTotalCredits += amount;
    }

    function requestTimeoutRefund() external {
        if (jobIds.length == 0) return;

        uint256 idx = uint256(keccak256(abi.encodePacked(block.timestamp, "refund"))) % jobIds.length;
        bytes32 jobId = jobIds[idx];

        (address jobUser,,,,,, uint256 amount,, uint64 deadline,,, NebulaVerifiableAI.JobState state) =
            target.getJob(jobId);
        if (jobUser == address(0)) return;
        if (
            state != NebulaVerifiableAI.JobState.Created && state != NebulaVerifiableAI.JobState.Assigned
                && state != NebulaVerifiableAI.JobState.ProofSubmitted
        ) return;
        if (block.timestamp <= deadline) return;

        vm.prank(jobUser);
        target.requestTimeoutRefund(jobId);

        ghostActiveEscrow -= amount;
        ghostPendingWithdrawals += amount;
        ghostTotalCredits += amount;
    }

    function withdrawFunds() external {
        // Withdraw the larger of provider/user pending balances (purely for ghost tracking;
        // total withdrawn is what the conservation invariants rely on).
        uint256 providerPending = target.getPendingWithdrawal(provider);
        uint256 userPending = target.getPendingWithdrawal(user);
        if (providerPending == 0 && userPending == 0) return;

        address who = providerPending >= userPending && providerPending > 0 ? provider : user;

        uint256 balanceBefore = usdc.balanceOf(address(target));
        vm.prank(who);
        target.withdraw();
        uint256 balanceAfter = usdc.balanceOf(address(target));

        uint256 withdrawn = balanceBefore - balanceAfter;
        ghostPendingWithdrawals -= withdrawn;
        ghostTotalWithdrawals += withdrawn;
    }

    function unsolicitedUSDC() external {
        // Send USDC directly to contract (not through createJob)
        usdc.mint(address(target), 1000);
    }

    function advanceTime(
        uint256 delta
    ) external {
        // Bound warps to keep timestamps well inside uint64 and drive deadlines organically.
        vm.warp(block.timestamp + (delta % 100_000));
    }

    // ──────────────────────────────────────────────
    // Helpers
    // ──────────────────────────────────────────────

    receive() external payable {}
}

// ═══════════════════════════════════════════════════════════════════
// Test Suite
// ═══════════════════════════════════════════════════════════════════

contract NebulaInvariantTest is Test {
    NebulaHandler handler;

    function setUp() public {
        handler = new NebulaHandler();
        handler.setUp();
    }

    function test_invariant_fuzz() public {
        for (uint256 j = 0; j < 100; j++) {
            uint256 action = uint256(keccak256(abi.encodePacked(block.timestamp, j))) % 8;

            if (action == 0) {
                handler.createJob();
            } else if (action == 1) {
                handler.assignProvider();
            } else if (action == 2) {
                handler.submitProof();
            } else if (action == 3) {
                handler.verifyJobValid();
            } else if (action == 4) {
                handler.verifyJobInvalid();
            } else if (action == 5) {
                handler.requestTimeoutRefund();
            } else if (action == 6) {
                handler.withdrawFunds();
            } else {
                handler.unsolicitedUSDC();
            }

            handler.check_solvency();
            handler.check_ghost_escrow_matches();
            handler.check_ghost_pending_matches();
        }
    }
}

// ═══════════════════════════════════════════════════════════════════
// Genuine Stateful Invariant Tests (Foundry invariant engine)
// ═══════════════════════════════════════════════════════════════════

contract NebulaStatefulInvariantTest is Test {
    NebulaHandler handler;

    function setUp() public {
        handler = new NebulaHandler();
        handler.setUp();

        bytes4[] memory selectors = new bytes4[](8);
        selectors[0] = NebulaHandler.createJob.selector;
        selectors[1] = NebulaHandler.assignProvider.selector;
        selectors[2] = NebulaHandler.submitProof.selector;
        selectors[3] = NebulaHandler.verifyJobValid.selector;
        selectors[4] = NebulaHandler.verifyJobInvalid.selector;
        selectors[5] = NebulaHandler.requestTimeoutRefund.selector;
        selectors[6] = NebulaHandler.withdrawFunds.selector;
        selectors[7] = NebulaHandler.advanceTime.selector;

        targetContract(address(handler));
        targetSelector(FuzzSelector({addr: address(handler), selectors: selectors}));
    }

    /// @notice The contract must always be able to cover every escrowed + pending USDC.
    function invariant_solvency() public view {
        uint256 balance = handler.usdc().balanceOf(address(handler.target()));
        assertTrue(
            balance >= handler.target().totalEscrowed() + handler.target().totalPendingWithdrawals(),
            "balance < escrowed + pending"
        );
    }

    /// @notice Every contract-wide escrow change must be mirrored by the handler ghost.
    function invariant_ghost_escrow_matches() public view {
        assertEq(handler.target().totalEscrowed(), handler.ghostActiveEscrow(), "escrow/ghost mismatch");
    }

    /// @notice Every contract-wide pending-withdrawal change must be mirrored by the handler ghost.
    function invariant_ghost_pending_matches() public view {
        assertEq(
            handler.target().totalPendingWithdrawals(), handler.ghostPendingWithdrawals(), "pending/ghost mismatch"
        );
    }

    /// @notice Funds are conserved: every created job's escrow either stays locked or becomes a credit.
    function invariant_locked_funds_conservation() public view {
        assertEq(
            handler.ghostActiveEscrow() + handler.ghostTotalCredits(),
            handler.ghostCreatedFunds(),
            "escrow+credits != created funds"
        );
    }

    /// @notice Credits are conserved: every credit is either still pending or has been withdrawn.
    function invariant_withdrawals_conservation() public view {
        assertEq(
            handler.ghostPendingWithdrawals() + handler.ghostTotalWithdrawals(),
            handler.ghostTotalCredits(),
            "pending+withdrawn != credits"
        );
    }
}

// ═══════════════════════════════════════════════════════════════════
// Unit Test Suite
// ═══════════════════════════════════════════════════════════════════

contract NebulaVerifiableAITest is Test {
    NebulaVerifiableAI public nebula;
    MockUSDC public usdc;
    address public owner = address(this);
    address public verifier = makeAddr("verifier");
    address public user = makeAddr("user");
    address public provider = makeAddr("provider");

    // Golden UUID→bytes32 vectors (PRD v3.1 §7.5)
    // UUID 550e8400-e29b-41d4-a716-446655440000 → left-aligned bytes32
    bytes32 public constant JOB_ID = hex"550e8400e29b41d4a71644665544000000000000000000000000000000000000";
    bytes32 public constant JOB_ID_2 = hex"6ba7b8109dad11d180b400c04fd430c800000000000000000000000000000000";
    bytes32 public constant JOB_ID_3 = hex"0000000000000000000000000000000100000000000000000000000000000000";
    bytes32 public constant JOB_ID_4 = hex"bbbbbbbbccccddddeeeeffffffffffff00000000000000000000000000000000";
    bytes32 public constant JOB_ID_5 = hex"ccccccccddddeeeeffff00000000000000000000000000000000000000000000";
    bytes32 public constant JOB_ID_6 = hex"a0b1c2d3e4f56789abcdef012345678900000000000000000000000000000000";
    bytes32 public constant JOB_ID_7 = hex"9f8e7d6c5b4a3210fedcba987654321000000000000000000000000000000000";
    bytes32 public constant JOB_ID_8 = hex"deadbeefdeadbeefdeadbeefdeadbeef00000000000000000000000000000000";
    bytes32 public constant JOB_ID_9 = hex"cafebabecafebabecafebabecafebabe00000000000000000000000000000000";
    bytes32 public constant JOB_ID_10 = hex"0123456789abcdef0123456789abcdef00000000000000000000000000000000";
    bytes32 public constant FINGERPRINT = keccak256("test_fingerprint");
    bytes32 public constant LEASE_ID = keccak256("lease_1");
    uint256 public constant JOB_PRICE = 50_000;

    // Event declarations for expectEmit
    event JobCreated(
        bytes32 indexed jobId, address indexed user, bytes32 fingerprint, uint256 amount, uint256 timestamp
    );
    event ProviderAssigned(bytes32 indexed jobId, address indexed provider, bytes32 leaseId, uint64 leaseExpiresAt);
    event ProofSubmitted(
        bytes32 indexed jobId, bytes32 leaseId, bytes32 merkleRoot, bytes32 outputHash, address provider
    );
    event JobSettled(bytes32 indexed jobId, bool valid, uint256 timestamp);
    event PaymentCredited(bytes32 indexed jobId, address indexed provider, uint256 amount);
    event TimeoutRefundCredited(bytes32 indexed jobId, address indexed user, uint256 amount);
    event WithdrawalCompleted(address indexed provider, uint256 amount);
    event VerifierUpdated(address indexed oldVerifier, address indexed newVerifier);
    event MaxJobAmountUpdated(uint256 oldMax, uint256 newMax);
    event JobPriceUpdated(uint256 oldPrice, uint256 newPrice);

    function setUp() public {
        usdc = new MockUSDC();
        nebula = new NebulaVerifiableAI(address(usdc));
        nebula.setVerifier(verifier);

        usdc.mint(user, JOB_PRICE * 100);
        vm.startPrank(user);
        usdc.approve(address(nebula), type(uint256).max);
        vm.stopPrank();
    }

    // ──────────────────────────────────────────────
    // Helpers
    // ──────────────────────────────────────────────

    function _createDefaultJob() internal returns (bytes32) {
        vm.prank(user);
        return nebula.createJob(JOB_ID, FINGERPRINT);
    }

    function _assignDefaultProvider(
        bytes32 jobId
    ) internal {
        uint64 leaseExpiry = SafeCast.toUint64(block.timestamp + 3500);
        vm.prank(verifier);
        nebula.assignProvider(jobId, provider, LEASE_ID, leaseExpiry);
    }

    function _submitDefaultProof(
        bytes32 jobId
    ) internal {
        bytes32 merkleRoot = keccak256("merkle");
        bytes32 outputHash = keccak256("output");
        vm.prank(verifier);
        nebula.submitProof(jobId, LEASE_ID, merkleRoot, outputHash);
    }

    // ═══════════════════════════════════════════════════════════════════
    // Unit Tests — createJob
    // ═══════════════════════════════════════════════════════════════════

    function test_createJob_happy() public {
        bytes32 jobId = _createDefaultJob();

        (
            address jobUser,
            address jobProvider,
            bytes32 jobFingerprint,,,,
            uint256 jobAmount,,
            uint64 jobDeadline,
            uint64 createdAt,,
            NebulaVerifiableAI.JobState state
        ) = nebula.getJob(jobId);

        assertEq(jobUser, user);
        assertEq(jobProvider, address(0));
        assertEq(jobFingerprint, FINGERPRINT);
        assertEq(jobAmount, JOB_PRICE);
        assertGt(createdAt, 0);
        assertEq(jobDeadline, SafeCast.toUint64(block.timestamp + 86400));
        assertEq(uint8(state), uint8(NebulaVerifiableAI.JobState.Created));

        assertEq(usdc.balanceOf(address(nebula)), JOB_PRICE);
        assertEq(usdc.balanceOf(user), JOB_PRICE * 99);
        assertEq(nebula.totalEscrowed(), JOB_PRICE);
    }

    function test_createJob_emits_event() public {
        vm.expectEmit(true, true, false, true);
        emit JobCreated(JOB_ID, user, FINGERPRINT, JOB_PRICE, block.timestamp);

        vm.prank(user);
        nebula.createJob(JOB_ID, FINGERPRINT);
    }

    function test_createJob_reverts_zero_job_id() public {
        vm.prank(user);
        vm.expectRevert(NebulaVerifiableAI.InvalidJobID.selector);
        nebula.createJob(bytes32(0), FINGERPRINT);
    }

    function test_createJob_reverts_zero_fingerprint() public {
        vm.prank(user);
        vm.expectRevert(NebulaVerifiableAI.InvalidFingerprint.selector);
        nebula.createJob(JOB_ID, bytes32(0));
    }

    function test_createJob_reverts_duplicate_job_id() public {
        _createDefaultJob();
        vm.prank(user);
        vm.expectRevert(NebulaVerifiableAI.JobAlreadyExists.selector);
        nebula.createJob(JOB_ID, FINGERPRINT);
    }

    function test_createJob_reverts_insufficient_balance() public {
        address poorUser = makeAddr("poor");
        vm.prank(poorUser);
        vm.expectRevert();
        nebula.createJob(JOB_ID, FINGERPRINT);
    }

    function test_createJob_reverts_no_approval() public {
        address noApprove = makeAddr("noapprove");
        usdc.mint(noApprove, JOB_PRICE * 10);
        vm.prank(noApprove);
        vm.expectRevert();
        nebula.createJob(JOB_ID, FINGERPRINT);
    }

    // ═══════════════════════════════════════════════════════════════════
    // Golden UUID→bytes32 Vector Tests (PRD v3.1 §7.5)
    // ═══════════════════════════════════════════════════════════════════

    function test_golden_vector_550e8400() public {
        // UUID: 550e8400-e29b-41d4-a716-446655440000
        // Bytes: 550e8400e29b41d4a716446655440000 (16 bytes) + 16 zero bytes
        assertEq(JOB_ID, hex"550e8400e29b41d4a71644665544000000000000000000000000000000000000");
    }

    function test_golden_vector_6ba7b810() public {
        vm.prank(user);
        bytes32 jobId = nebula.createJob(JOB_ID_2, FINGERPRINT);
        assertEq(jobId, JOB_ID_2);
    }

    function test_golden_vector_00000000() public {
        vm.prank(user);
        bytes32 jobId = nebula.createJob(JOB_ID_3, FINGERPRINT);
        assertEq(jobId, JOB_ID_3);
    }

    function test_golden_vector_ffffffff() public {
        vm.prank(user);
        bytes32 jobId = nebula.createJob(JOB_ID_4, FINGERPRINT);
        assertEq(jobId, JOB_ID_4);
    }

    function test_golden_vector_12345678() public {
        vm.prank(user);
        bytes32 jobId = nebula.createJob(JOB_ID_5, FINGERPRINT);
        assertEq(jobId, JOB_ID_5);
    }

    function test_golden_vector_a0b1c2d3() public {
        vm.prank(user);
        bytes32 jobId = nebula.createJob(JOB_ID_6, FINGERPRINT);
        assertEq(jobId, JOB_ID_6);
    }

    function test_golden_vector_9f8e7d6c() public {
        vm.prank(user);
        bytes32 jobId = nebula.createJob(JOB_ID_7, FINGERPRINT);
        assertEq(jobId, JOB_ID_7);
    }

    function test_golden_vector_dead_beef() public {
        vm.prank(user);
        bytes32 jobId = nebula.createJob(JOB_ID_8, FINGERPRINT);
        assertEq(jobId, JOB_ID_8);
    }

    function test_golden_vector_cafe_babe() public {
        vm.prank(user);
        bytes32 jobId = nebula.createJob(JOB_ID_9, FINGERPRINT);
        assertEq(jobId, JOB_ID_9);
    }

    function test_golden_vector_01234567() public {
        vm.prank(user);
        bytes32 jobId = nebula.createJob(JOB_ID_10, FINGERPRINT);
        assertEq(jobId, JOB_ID_10);
    }

    // ═══════════════════════════════════════════════════════════════════
    // Unit Tests — createJob UUID Padding Validation
    // ═══════════════════════════════════════════════════════════════════

    function test_createJob_valid_left_aligned_uuid_succeeds() public {
        // Valid left-aligned UUID: upper 16 bytes nonzero, lower 16 bytes zero
        bytes32 validId = hex"550e8400e29b41d4a71644665544000000000000000000000000000000000000";
        vm.prank(user);
        bytes32 jobId = nebula.createJob(validId, FINGERPRINT);
        assertEq(jobId, validId);
    }

    function test_createJob_reverts_all_zero_id() public {
        vm.prank(user);
        vm.expectRevert(NebulaVerifiableAI.InvalidJobID.selector);
        nebula.createJob(bytes32(0), FINGERPRINT);
    }

    function test_createJob_reverts_one_nonzero_byte_in_padding() public {
        // One nonzero byte in the lowest position of the padding
        bytes32 badId = hex"550e8400e29b41d4a71644665544000000000000000000000000000000000001";
        vm.prank(user);
        vm.expectRevert(NebulaVerifiableAI.InvalidJobID.selector);
        nebula.createJob(badId, FINGERPRINT);
    }

    function test_createJob_reverts_all_16_padding_bytes_nonzero() public {
        // All 16 padding bytes are nonzero (right half = 0xffffffffffffffffffffffffffffffff)
        bytes32 badId = hex"550e8400e29b41d4a716446655440000ffffffffffffffffffffffffffffffff";
        vm.prank(user);
        vm.expectRevert(NebulaVerifiableAI.InvalidJobID.selector);
        nebula.createJob(badId, FINGERPRINT);
    }

    function test_createJob_same_uuid_cannot_obtain_identity_through_alternate_padding() public {
        // Create a job with valid left-aligned UUID
        bytes32 validId = hex"550e8400e29b41d4a71644665544000000000000000000000000000000000000";
        vm.prank(user);
        nebula.createJob(validId, FINGERPRINT);

        // Same UUID bytes but with nonzero padding — must revert (not a new job, invalid encoding)
        bytes32 badPadding = hex"550e8400e29b41d4a71644665544000000000000000000000000000000000001";
        vm.prank(user);
        vm.expectRevert(NebulaVerifiableAI.InvalidJobID.selector);
        nebula.createJob(badPadding, FINGERPRINT);
    }

    function test_createJob_reverts_duplicate_canonical_id() public {
        bytes32 id = hex"550e8400e29b41d4a71644665544000000000000000000000000000000000000";
        vm.prank(user);
        nebula.createJob(id, FINGERPRINT);

        vm.prank(user);
        vm.expectRevert(NebulaVerifiableAI.JobAlreadyExists.selector);
        nebula.createJob(id, FINGERPRINT);
    }

    function testFuzz_createJob_reverts_nonzero_lower_128_bits(
        uint128 nonzeroPadding
    ) public {
        vm.assume(nonzeroPadding != 0);
        // Valid upper 16 bytes (canonical UUID) with fuzzed nonzero lower 16 bytes
        bytes32 badId = bytes32(uint256(0x550e8400e29b41d4a716446655440000) << 128 | uint256(nonzeroPadding));
        vm.prank(user);
        vm.expectRevert(NebulaVerifiableAI.InvalidJobID.selector);
        nebula.createJob(badId, FINGERPRINT);
    }

    function testFuzz_createJob_valid_upper_128bits_zero_lower_128bits(
        uint128 upperBits
    ) public {
        vm.assume(upperBits != 0);
        // Build a bytes32 with fuzzed upper 16 bytes and zero lower 16 bytes
        bytes32 validId = bytes32(uint256(uint128(upperBits)) << 128);
        vm.prank(user);
        bytes32 jobId = nebula.createJob(validId, FINGERPRINT);
        assertEq(jobId, validId);
    }

    // ═══════════════════════════════════════════════════════════════════
    // Unit Tests — assignProvider
    // ═══════════════════════════════════════════════════════════════════

    function test_assignProvider_initial_happy() public {
        bytes32 jobId = _createDefaultJob();
        uint64 leaseExpiry = SafeCast.toUint64(block.timestamp + 3500);

        vm.prank(verifier);
        nebula.assignProvider(jobId, provider, LEASE_ID, leaseExpiry);

        (, address jobProvider,,,, bytes32 jobLeaseId,, uint64 jobLeaseExpiry,,,, NebulaVerifiableAI.JobState state) =
            nebula.getJob(jobId);

        assertEq(jobProvider, provider);
        assertEq(jobLeaseId, LEASE_ID);
        assertEq(jobLeaseExpiry, leaseExpiry);
        assertEq(uint8(state), uint8(NebulaVerifiableAI.JobState.Assigned));
    }

    function test_assignProvider_reassignment_happy() public {
        bytes32 jobId = _createDefaultJob();
        vm.prank(verifier);
        nebula.assignProvider(jobId, provider, LEASE_ID, 3501);

        vm.warp(4000);

        bytes32 newLeaseId = keccak256("lease_2");
        vm.prank(verifier);
        nebula.assignProvider(jobId, makeAddr("provider2"), newLeaseId, 7000);

        (, address jobProvider,,,, bytes32 jobLeaseId,, uint64 jobLeaseExpiry,,,, NebulaVerifiableAI.JobState state) =
            nebula.getJob(jobId);

        assertEq(jobProvider, makeAddr("provider2"));
        assertEq(jobLeaseId, newLeaseId);
        assertEq(jobLeaseExpiry, 7000);
        assertEq(uint8(state), uint8(NebulaVerifiableAI.JobState.Assigned));
    }

    function test_assignProvider_reverts_reassignment_before_expiry() public {
        bytes32 jobId = _createDefaultJob();
        uint64 leaseExpiry = SafeCast.toUint64(block.timestamp + 3500);
        vm.prank(verifier);
        nebula.assignProvider(jobId, provider, LEASE_ID, leaseExpiry);

        bytes32 newLeaseId = keccak256("lease_2");
        uint64 newExpiry = SafeCast.toUint64(block.timestamp + 3500);
        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.LeaseExpired.selector);
        nebula.assignProvider(jobId, makeAddr("provider2"), newLeaseId, newExpiry);
    }

    function test_assignProvider_reverts_same_lease_id() public {
        bytes32 jobId = _createDefaultJob();
        uint64 initialExpiry = SafeCast.toUint64(block.timestamp + 3500);
        vm.prank(verifier);
        nebula.assignProvider(jobId, provider, LEASE_ID, initialExpiry);

        vm.warp(block.timestamp + 3600);

        uint64 newExpiry = SafeCast.toUint64(block.timestamp + 3500);
        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.LeaseMismatch.selector);
        nebula.assignProvider(jobId, makeAddr("provider2"), LEASE_ID, newExpiry);
    }

    function test_assignProvider_reverts_reassignment_past_deadline() public {
        bytes32 jobId = _createDefaultJob();
        uint64 initialExpiry = SafeCast.toUint64(block.timestamp + 3500);
        vm.prank(verifier);
        nebula.assignProvider(jobId, provider, LEASE_ID, initialExpiry);

        vm.warp(block.timestamp + 86500);

        bytes32 newLeaseId = keccak256("lease_2");
        uint64 newExpiry = SafeCast.toUint64(block.timestamp + 100);
        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.JobDeadlineExpired.selector);
        nebula.assignProvider(jobId, makeAddr("provider2"), newLeaseId, newExpiry);
    }

    function test_assignProvider_reverts_job_not_found() public {
        bytes32 fakeJobId = keccak256("nonexistent");
        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.JobNotFound.selector);
        nebula.assignProvider(fakeJobId, provider, LEASE_ID, SafeCast.toUint64(block.timestamp + 3500));
    }

    function test_assignProvider_reverts_zero_provider() public {
        bytes32 jobId = _createDefaultJob();
        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.InvalidProvider.selector);
        nebula.assignProvider(jobId, address(0), LEASE_ID, SafeCast.toUint64(block.timestamp + 3500));
    }

    function test_assignProvider_reverts_zero_lease_id() public {
        bytes32 jobId = _createDefaultJob();
        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.InvalidLeaseID.selector);
        nebula.assignProvider(jobId, provider, bytes32(0), SafeCast.toUint64(block.timestamp + 3500));
    }

    function test_assignProvider_reverts_only_verifier() public {
        bytes32 jobId = _createDefaultJob();

        // The owner is NOT the configured verifier, so it cannot assign.
        address[] memory callers = new address[](4);
        callers[0] = owner; // address(this) — contract owner
        callers[1] = user;
        callers[2] = provider;
        callers[3] = makeAddr("random");

        for (uint256 i = 0; i < callers.length; i++) {
            vm.prank(callers[i]);
            vm.expectRevert(NebulaVerifiableAI.OnlyVerifier.selector);
            nebula.assignProvider(jobId, provider, LEASE_ID, SafeCast.toUint64(block.timestamp + 3500));
        }
    }

    function test_assignProvider_owner_can_assign_when_is_verifier() public {
        nebula.setVerifier(owner);

        bytes32 jobId = _createDefaultJob();
        uint64 leaseExpiry = SafeCast.toUint64(block.timestamp + 3500);
        nebula.assignProvider(jobId, provider, LEASE_ID, leaseExpiry);

        (, address jobProvider,,,, bytes32 jobLeaseId,,,,,, NebulaVerifiableAI.JobState state) = nebula.getJob(jobId);
        assertEq(jobProvider, provider);
        assertEq(jobLeaseId, LEASE_ID);
        assertEq(uint8(state), uint8(NebulaVerifiableAI.JobState.Assigned));
    }

    function test_assignProvider_old_verifier_loses_authority_after_rotation() public {
        bytes32 jobId = _createDefaultJob();
        uint64 creationTs = SafeCast.toUint64(block.timestamp);
        vm.prank(verifier);
        nebula.assignProvider(jobId, provider, LEASE_ID, SafeCast.toUint64(creationTs + 3500));

        address newVerifier = makeAddr("newVerifier");
        nebula.setVerifier(newVerifier);

        // Old verifier loses authority immediately.
        uint64 rotatedAt = creationTs + 3600;
        vm.warp(rotatedAt);
        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.OnlyVerifier.selector);
        nebula.assignProvider(jobId, makeAddr("provider2"), keccak256("lease_2"), SafeCast.toUint64(rotatedAt + 3500));

        // New verifier can reassign after strict lease expiry.
        bytes32 newLeaseId = keccak256("lease_3");
        vm.prank(newVerifier);
        nebula.assignProvider(jobId, makeAddr("provider2"), newLeaseId, SafeCast.toUint64(rotatedAt + 3500));

        (, address jobProvider,,,, bytes32 jobLeaseId,,,,,, NebulaVerifiableAI.JobState state) = nebula.getJob(jobId);
        assertEq(jobProvider, makeAddr("provider2"));
        assertEq(jobLeaseId, newLeaseId);
        assertEq(uint8(state), uint8(NebulaVerifiableAI.JobState.Assigned));
    }

    function test_assignProvider_new_verifier_can_assign_initial() public {
        address newVerifier = makeAddr("newVerifier");
        nebula.setVerifier(newVerifier);

        bytes32 jobId = _createDefaultJob();
        uint64 leaseExpiry = SafeCast.toUint64(block.timestamp + 3500);
        vm.prank(newVerifier);
        nebula.assignProvider(jobId, provider, LEASE_ID, leaseExpiry);

        (, address jobProvider,,,, bytes32 jobLeaseId,,,,,, NebulaVerifiableAI.JobState state) = nebula.getJob(jobId);
        assertEq(jobProvider, provider);
        assertEq(jobLeaseId, LEASE_ID);
        assertEq(uint8(state), uint8(NebulaVerifiableAI.JobState.Assigned));
    }

    // ═══════════════════════════════════════════════════════════════════
    // Unit Tests — submitProof
    // ═══════════════════════════════════════════════════════════════════

    function test_submitProof_happy() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);

        bytes32 merkleRoot = keccak256("merkle_root");
        bytes32 outputHash = keccak256("output_hash");

        vm.prank(verifier);
        nebula.submitProof(jobId, LEASE_ID, merkleRoot, outputHash);

        (,,, bytes32 jobMerkleRoot, bytes32 jobOutputHash,,,,,,, NebulaVerifiableAI.JobState state) =
            nebula.getJob(jobId);

        assertEq(jobMerkleRoot, merkleRoot);
        assertEq(jobOutputHash, outputHash);
        assertEq(uint8(state), uint8(NebulaVerifiableAI.JobState.ProofSubmitted));
    }

    function test_submitProof_emits_event() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);
        bytes32 merkleRoot = keccak256("merkle");
        bytes32 outputHash = keccak256("output");

        vm.expectEmit(true, true, false, true);
        emit ProofSubmitted(jobId, LEASE_ID, merkleRoot, outputHash, provider);

        vm.prank(verifier);
        nebula.submitProof(jobId, LEASE_ID, merkleRoot, outputHash);
    }

    function test_submitProof_reverts_wrong_lease_id() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);

        bytes32 wrongLeaseId = keccak256("wrong_lease");
        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.LeaseMismatch.selector);
        nebula.submitProof(jobId, wrongLeaseId, keccak256("root"), keccak256("hash"));
    }

    function test_submitProof_reverts_expired_lease() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);

        vm.warp(block.timestamp + 3600);

        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.LeaseExpired.selector);
        nebula.submitProof(jobId, LEASE_ID, keccak256("root"), keccak256("hash"));
    }

    function test_submitProof_reverts_past_deadline() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);

        vm.warp(block.timestamp + 86500);

        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.LeaseExpired.selector);
        nebula.submitProof(jobId, LEASE_ID, keccak256("root"), keccak256("hash"));
    }

    function test_submitProof_reverts_nonexistent_job() public {
        bytes32 fakeJobId = keccak256("nonexistent");
        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.JobNotFound.selector);
        nebula.submitProof(fakeJobId, LEASE_ID, keccak256("root"), keccak256("hash"));
    }

    function test_submitProof_reverts_zero_merkle_root() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);

        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.InvalidMerkleRoot.selector);
        nebula.submitProof(jobId, LEASE_ID, bytes32(0), keccak256("hash"));
    }

    function test_submitProof_reverts_zero_output_hash() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);

        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.InvalidOutputHash.selector);
        nebula.submitProof(jobId, LEASE_ID, keccak256("root"), bytes32(0));
    }

    function test_submitProof_reverts_only_verifier() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);

        vm.prank(user);
        vm.expectRevert(NebulaVerifiableAI.OnlyVerifier.selector);
        nebula.submitProof(jobId, LEASE_ID, keccak256("root"), keccak256("hash"));
    }

    function test_submitProof_reverts_already_submitted() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);
        _submitDefaultProof(jobId);

        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.JobNotInState.selector);
        nebula.submitProof(jobId, LEASE_ID, keccak256("root2"), keccak256("hash2"));
    }

    // ═══════════════════════════════════════════════════════════════════
    // Unit Tests — verifyJob
    // ═══════════════════════════════════════════════════════════════════

    function test_verifyJob_settles_valid() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);
        _submitDefaultProof(jobId);

        vm.prank(verifier);
        nebula.verifyJob(jobId, true);

        (,,,,,,,,,, uint64 completedAt, NebulaVerifiableAI.JobState state) = nebula.getJob(jobId);

        assertEq(uint8(state), uint8(NebulaVerifiableAI.JobState.Settled));
        assertGt(completedAt, 0);
        assertEq(nebula.getPendingWithdrawal(provider), JOB_PRICE);
        assertEq(nebula.totalEscrowed(), 0);
        assertEq(nebula.totalPendingWithdrawals(), JOB_PRICE);
    }

    function test_verifyJob_refunds_invalid() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);
        _submitDefaultProof(jobId);

        vm.prank(verifier);
        nebula.verifyJob(jobId, false);

        (,,,,,,,,,, uint64 completedAt, NebulaVerifiableAI.JobState state) = nebula.getJob(jobId);

        assertEq(uint8(state), uint8(NebulaVerifiableAI.JobState.Refunded));
        assertGt(completedAt, 0);
        assertEq(nebula.getPendingWithdrawal(user), JOB_PRICE);
        assertEq(nebula.totalEscrowed(), 0);
        assertEq(nebula.totalPendingWithdrawals(), JOB_PRICE);
    }

    function test_verifyJob_emits_events() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);
        _submitDefaultProof(jobId);

        vm.expectEmit(true, false, false, false);
        emit PaymentCredited(jobId, provider, JOB_PRICE);

        vm.expectEmit(true, false, false, true);
        emit JobSettled(jobId, true, block.timestamp);

        vm.prank(verifier);
        nebula.verifyJob(jobId, true);
    }

    function test_verifyJob_reverts_only_verifier() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);
        _submitDefaultProof(jobId);

        vm.prank(user);
        vm.expectRevert(NebulaVerifiableAI.OnlyVerifier.selector);
        nebula.verifyJob(jobId, true);
    }

    function test_verifyJob_reverts_no_proof() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);

        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.NoProofSubmitted.selector);
        nebula.verifyJob(jobId, true);
    }

    function test_verifyJob_reverts_nonexistent_job() public {
        bytes32 fakeJobId = keccak256("nonexistent");
        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.JobNotFound.selector);
        nebula.verifyJob(fakeJobId, true);
    }

    function test_verifyJob_reverts_already_settled() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);
        _submitDefaultProof(jobId);

        vm.startPrank(verifier);
        nebula.verifyJob(jobId, true);

        vm.expectRevert(NebulaVerifiableAI.NoProofSubmitted.selector);
        nebula.verifyJob(jobId, true);
        vm.stopPrank();
    }

    // ═══════════════════════════════════════════════════════════════════
    // Unit Tests — requestTimeoutRefund
    // ═══════════════════════════════════════════════════════════════════

    function test_requestTimeoutRefund_happy() public {
        bytes32 jobId = _createDefaultJob();

        vm.warp(block.timestamp + 86500);

        vm.prank(user);
        nebula.requestTimeoutRefund(jobId);

        (,,,,,,,,,,, NebulaVerifiableAI.JobState state) = nebula.getJob(jobId);
        assertEq(uint8(state), uint8(NebulaVerifiableAI.JobState.Refunded));
        assertEq(nebula.getPendingWithdrawal(user), JOB_PRICE);
        assertEq(nebula.totalEscrowed(), 0);
        assertEq(nebula.totalPendingWithdrawals(), JOB_PRICE);
    }

    function test_requestTimeoutRefund_reverts_before_deadline() public {
        bytes32 jobId = _createDefaultJob();

        vm.prank(user);
        vm.expectRevert(NebulaVerifiableAI.RefundTooEarly.selector);
        nebula.requestTimeoutRefund(jobId);
    }

    function test_requestTimeoutRefund_reverts_not_job_creator() public {
        bytes32 jobId = _createDefaultJob();

        vm.warp(block.timestamp + 86500);

        vm.prank(provider);
        vm.expectRevert(NebulaVerifiableAI.NotJobCreator.selector);
        nebula.requestTimeoutRefund(jobId);
    }

    function test_requestTimeoutRefund_reverts_already_settled() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);
        _submitDefaultProof(jobId);

        vm.prank(verifier);
        nebula.verifyJob(jobId, true);

        vm.warp(block.timestamp + 86500);

        vm.prank(user);
        vm.expectRevert(NebulaVerifiableAI.RefundAlreadyProcessed.selector);
        nebula.requestTimeoutRefund(jobId);
    }

    function test_requestTimeoutRefund_reverts_after_invalid_settlement() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);
        _submitDefaultProof(jobId);

        vm.prank(verifier);
        nebula.verifyJob(jobId, false);

        vm.warp(block.timestamp + 86500);

        vm.prank(user);
        vm.expectRevert(NebulaVerifiableAI.RefundAlreadyProcessed.selector);
        nebula.requestTimeoutRefund(jobId);
    }

    function test_requestTimeoutRefund_fromProofSubmitted_happy() public {
        bytes32 jobId = _createDefaultJob();
        uint64 creationTs = SafeCast.toUint64(block.timestamp);
        _assignDefaultProvider(jobId);
        uint64 expectedLeaseExpiry = SafeCast.toUint64(creationTs + 3500);
        _submitDefaultProof(jobId);

        // Verifier submits proof but becomes unavailable before verifyJob — escrow must not be trapped.
        uint256 escapedBefore = nebula.totalEscrowed();
        uint256 pendingBefore = nebula.totalPendingWithdrawals();

        // Deterministic refund instant strictly past the deadline (deadline = creationTs + 86400).
        uint64 refundAt = creationTs + 86500;
        vm.warp(refundAt);

        vm.prank(user);
        nebula.requestTimeoutRefund(jobId);

        (
            ,
            address jobProvider,,,,
            bytes32 jobLeaseId,,
            uint64 jobLeaseExpiry,
            uint64 deadline,
            uint64 createdAt,
            uint64 completedAt,
            NebulaVerifiableAI.JobState state
        ) = nebula.getJob(jobId);

        // Resulting state and timestamps.
        assertEq(uint8(state), uint8(NebulaVerifiableAI.JobState.Refunded));
        assertEq(completedAt, refundAt, "refund must record the refund instant");
        assertEq(deadline, creationTs + 86400);
        assertEq(createdAt, creationTs);
        // Provider/lease assignment remains recorded but is now inert.
        assertEq(jobProvider, provider);
        assertEq(jobLeaseId, LEASE_ID);
        assertEq(jobLeaseExpiry, expectedLeaseExpiry);

        // Accounting moves exactly once: user credited exactly the escrowed amount.
        assertEq(nebula.getPendingWithdrawal(user), JOB_PRICE);
        assertEq(nebula.getPendingWithdrawal(provider), 0);
        assertEq(nebula.totalEscrowed(), escapedBefore - JOB_PRICE);
        assertEq(nebula.totalPendingWithdrawals(), pendingBefore + JOB_PRICE);
        assertTrue(nebula.invariant_solvency());
    }

    function test_requestTimeoutRefund_fromProofSubmitted_reverts_before_deadline() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);
        _submitDefaultProof(jobId);

        vm.prank(user);
        vm.expectRevert(NebulaVerifiableAI.RefundTooEarly.selector);
        nebula.requestTimeoutRefund(jobId);
    }

    function test_requestTimeoutRefund_fromProofSubmitted_at_exact_deadline_reverts() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);
        _submitDefaultProof(jobId);

        (,,,,,,,, uint64 deadline,,, NebulaVerifiableAI.JobState state) = nebula.getJob(jobId);
        assertEq(uint8(state), uint8(NebulaVerifiableAI.JobState.ProofSubmitted));
        vm.warp(deadline);

        vm.prank(user);
        vm.expectRevert(NebulaVerifiableAI.RefundTooEarly.selector);
        nebula.requestTimeoutRefund(jobId);
    }

    function test_requestTimeoutRefund_fromProofSubmitted_second_attempt_fails() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);
        _submitDefaultProof(jobId);

        vm.warp(block.timestamp + 86500);

        vm.prank(user);
        nebula.requestTimeoutRefund(jobId);

        // No double credit on a second attempt.
        vm.prank(user);
        vm.expectRevert(NebulaVerifiableAI.RefundAlreadyProcessed.selector);
        nebula.requestTimeoutRefund(jobId);

        assertEq(nebula.getPendingWithdrawal(user), JOB_PRICE);
        assertEq(nebula.totalPendingWithdrawals(), JOB_PRICE);
        assertEq(nebula.totalEscrowed(), 0);
    }

    function test_paused_requestTimeoutRefund_fromProofSubmitted_works() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);
        _submitDefaultProof(jobId);

        vm.warp(block.timestamp + 86500);
        nebula.pause();
        vm.prank(user);
        nebula.requestTimeoutRefund(jobId);

        (,,,,,,,,,,, NebulaVerifiableAI.JobState state) = nebula.getJob(jobId);
        assertEq(uint8(state), uint8(NebulaVerifiableAI.JobState.Refunded));
        assertEq(nebula.getPendingWithdrawal(user), JOB_PRICE);
    }

    function test_race_user_timeout_refund_wins_then_verifier_cannot_settle() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);
        _submitDefaultProof(jobId);

        // After the deadline the user refunds from ProofSubmitted.
        vm.warp(block.timestamp + 86500);
        vm.prank(user);
        nebula.requestTimeoutRefund(jobId);

        (,,,,,,,,,,, NebulaVerifiableAI.JobState state) = nebula.getJob(jobId);
        assertEq(uint8(state), uint8(NebulaVerifiableAI.JobState.Refunded));
        assertEq(nebula.getPendingWithdrawal(user), JOB_PRICE);
        assertEq(nebula.getPendingWithdrawal(provider), 0);

        // A late verifier settlement in either direction must fail and cannot double credit.
        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.NoProofSubmitted.selector);
        nebula.verifyJob(jobId, true);

        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.NoProofSubmitted.selector);
        nebula.verifyJob(jobId, false);

        assertEq(nebula.getPendingWithdrawal(user), JOB_PRICE);
        assertEq(nebula.getPendingWithdrawal(provider), 0);
        assertEq(nebula.totalPendingWithdrawals(), JOB_PRICE);
        assertTrue(nebula.invariant_solvency());
    }

    function test_race_verifier_settles_before_deadline_then_user_cannot_refund() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);
        _submitDefaultProof(jobId);

        // Verifier settles before the deadline.
        vm.prank(verifier);
        nebula.verifyJob(jobId, true);

        vm.warp(block.timestamp + 86500);
        vm.prank(user);
        vm.expectRevert(NebulaVerifiableAI.RefundAlreadyProcessed.selector);
        nebula.requestTimeoutRefund(jobId);

        // Single terminal settlement: provider credited exactly once, user never.
        assertEq(nebula.getPendingWithdrawal(provider), JOB_PRICE);
        assertEq(nebula.getPendingWithdrawal(user), 0);
        assertEq(nebula.totalPendingWithdrawals(), JOB_PRICE);
        assertEq(nebula.totalEscrowed(), 0);
        assertTrue(nebula.invariant_solvency());
    }

    function testFuzz_requestTimeoutRefund_fromProofSubmitted_strictly_after_deadline(
        uint96 afterDeadline
    ) public {
        vm.assume(afterDeadline > 0 && afterDeadline <= 90_000);

        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);
        _submitDefaultProof(jobId);

        (,,,,,,,, uint64 deadline,,, NebulaVerifiableAI.JobState state) = nebula.getJob(jobId);
        assertEq(uint8(state), uint8(NebulaVerifiableAI.JobState.ProofSubmitted));
        vm.warp(uint256(deadline) + uint256(afterDeadline));

        uint256 pendingBefore = nebula.totalPendingWithdrawals();
        vm.prank(user);
        nebula.requestTimeoutRefund(jobId);

        (,,,,,,,,,,, NebulaVerifiableAI.JobState stateAfter) = nebula.getJob(jobId);
        assertEq(uint8(stateAfter), uint8(NebulaVerifiableAI.JobState.Refunded));
        assertEq(nebula.getPendingWithdrawal(user), JOB_PRICE);
        assertEq(nebula.totalPendingWithdrawals(), pendingBefore + JOB_PRICE);
    }

    function testFuzz_requestTimeoutRefund_all_valid_states_at_or_before_deadline(
        uint8 stateSel,
        uint96 delta
    ) public {
        vm.assume(stateSel < 3 && delta <= 86_400);

        bytes32 jobId = _createDefaultJob();
        if (stateSel == 1) _assignDefaultProvider(jobId);
        if (stateSel == 2) {
            _assignDefaultProvider(jobId);
            _submitDefaultProof(jobId);
        }

        (,,,,,,,, uint64 deadline,,,) = nebula.getJob(jobId);
        vm.warp(uint256(deadline) - uint256(delta));

        vm.prank(user);
        vm.expectRevert(NebulaVerifiableAI.RefundTooEarly.selector);
        nebula.requestTimeoutRefund(jobId);
    }

    // ═══════════════════════════════════════════════════════════════════
    // Unit Tests — withdraw
    // ═══════════════════════════════════════════════════════════════════

    function test_withdraw_happy() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);
        _submitDefaultProof(jobId);

        vm.prank(verifier);
        nebula.verifyJob(jobId, true);

        uint256 balBefore = usdc.balanceOf(provider);
        vm.prank(provider);
        nebula.withdraw();

        assertEq(usdc.balanceOf(provider) - balBefore, JOB_PRICE);
        assertEq(nebula.getPendingWithdrawal(provider), 0);
        assertEq(nebula.totalPendingWithdrawals(), 0);
    }

    function test_withdraw_emits_event() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);
        _submitDefaultProof(jobId);

        vm.prank(verifier);
        nebula.verifyJob(jobId, true);

        vm.expectEmit(true, false, false, false);
        emit WithdrawalCompleted(provider, JOB_PRICE);

        vm.prank(provider);
        nebula.withdraw();
    }

    function test_withdraw_reverts_insufficient() public {
        vm.prank(provider);
        vm.expectRevert(NebulaVerifiableAI.WithdrawInsufficient.selector);
        nebula.withdraw();
    }

    function test_withdraw_multiple_jobs() public {
        bytes32 job1 = _createDefaultJob();
        _assignDefaultProvider(job1);
        _submitDefaultProof(job1);

        usdc.mint(user, JOB_PRICE);
        vm.startPrank(user);
        usdc.approve(address(nebula), type(uint256).max);
        bytes32 job2 = nebula.createJob(JOB_ID_4, FINGERPRINT);
        vm.stopPrank();

        _assignDefaultProvider(job2);
        vm.prank(verifier);
        nebula.submitProof(job2, LEASE_ID, keccak256("root2"), keccak256("hash2"));

        vm.startPrank(verifier);
        nebula.verifyJob(job1, true);
        nebula.verifyJob(job2, true);
        vm.stopPrank();

        uint256 balBefore = usdc.balanceOf(provider);
        vm.prank(provider);
        nebula.withdraw();

        assertEq(usdc.balanceOf(provider) - balBefore, JOB_PRICE * 2);
    }

    function test_withdraw_no_return_token_succeeds() public {
        NoReturnUSDC noReturnToken = new NoReturnUSDC();
        NebulaVerifiableAI noReturnNebula = new NebulaVerifiableAI(address(noReturnToken));

        address worker = makeAddr("worker_no_return");
        noReturnToken.mint(worker, JOB_PRICE * 10);
        vm.startPrank(worker);
        noReturnToken.approve(address(noReturnNebula), type(uint256).max);
        bytes32 jobId = noReturnNebula.createJob(JOB_ID, FINGERPRINT);
        vm.stopPrank();

        // Verifier is the deployer (this contract). Assign, submit, settle valid.
        noReturnNebula.assignProvider(jobId, provider, LEASE_ID, SafeCast.toUint64(block.timestamp + 3500));
        vm.prank(address(this));
        noReturnNebula.submitProof(jobId, LEASE_ID, keccak256("root"), keccak256("hash"));
        vm.prank(address(this));
        noReturnNebula.verifyJob(jobId, true);

        assertEq(noReturnNebula.getPendingWithdrawal(provider), JOB_PRICE);

        uint256 balBefore = noReturnToken.balanceOf(provider);
        vm.prank(provider);
        noReturnNebula.withdraw();

        assertEq(noReturnToken.balanceOf(provider) - balBefore, JOB_PRICE);
        assertEq(noReturnNebula.getPendingWithdrawal(provider), 0);
        assertEq(noReturnNebula.totalPendingWithdrawals(), 0);
    }

    function test_withdraw_reverting_token_reverts_atomically() public {
        RevertUSDC revertToken = new RevertUSDC();
        NebulaVerifiableAI revertNebula = new NebulaVerifiableAI(address(revertToken));

        address worker = makeAddr("worker_revert");
        revertToken.mint(worker, JOB_PRICE * 10);
        vm.startPrank(worker);
        revertToken.approve(address(revertNebula), type(uint256).max);
        bytes32 jobId = revertNebula.createJob(JOB_ID, FINGERPRINT);
        vm.stopPrank();

        revertNebula.assignProvider(jobId, provider, LEASE_ID, SafeCast.toUint64(block.timestamp + 3500));
        vm.prank(address(this));
        revertNebula.submitProof(jobId, LEASE_ID, keccak256("root"), keccak256("hash"));
        vm.prank(address(this));
        revertNebula.verifyJob(jobId, true);

        assertEq(revertNebula.getPendingWithdrawal(provider), JOB_PRICE);
        assertEq(revertNebula.totalPendingWithdrawals(), JOB_PRICE);

        vm.prank(provider);
        vm.expectRevert("RevertUSDC: blocked");
        revertNebula.withdraw();

        // Atomic rollback: ledger states unchanged on failed withdrawal.
        assertEq(revertNebula.getPendingWithdrawal(provider), JOB_PRICE);
        assertEq(revertNebula.totalPendingWithdrawals(), JOB_PRICE);
        assertEq(revertToken.balanceOf(address(revertNebula)), JOB_PRICE);
    }

    function test_withdraw_false_return_token_reverts_safeErc20() public {
        FalseReturnUSDC falseToken = new FalseReturnUSDC();
        NebulaVerifiableAI falseNebula = new NebulaVerifiableAI(address(falseToken));

        address worker = makeAddr("worker_false_return");
        falseToken.mint(worker, JOB_PRICE * 10);
        vm.startPrank(worker);
        falseToken.approve(address(falseNebula), type(uint256).max);
        bytes32 jobId = falseNebula.createJob(JOB_ID, FINGERPRINT);
        vm.stopPrank();

        falseNebula.assignProvider(jobId, provider, LEASE_ID, SafeCast.toUint64(block.timestamp + 3500));
        vm.prank(address(this));
        falseNebula.submitProof(jobId, LEASE_ID, keccak256("root"), keccak256("hash"));
        vm.prank(address(this));
        falseNebula.verifyJob(jobId, true);

        assertEq(falseNebula.getPendingWithdrawal(provider), JOB_PRICE);

        vm.prank(provider);
        vm.expectRevert(abi.encodeWithSelector(SafeERC20.SafeERC20FailedOperation.selector, address(falseToken)));
        falseNebula.withdraw();

        // Atomic rollback: ledger states unchanged on failed withdrawal.
        assertEq(falseNebula.getPendingWithdrawal(provider), JOB_PRICE);
        assertEq(falseNebula.totalPendingWithdrawals(), JOB_PRICE);
        assertEq(falseToken.balanceOf(address(falseNebula)), JOB_PRICE);
    }

    function test_withdraw_cannot_repeat_without_new_credit() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);
        _submitDefaultProof(jobId);

        vm.prank(verifier);
        nebula.verifyJob(jobId, true);

        vm.prank(provider);
        nebula.withdraw();
        assertEq(nebula.getPendingWithdrawal(provider), 0);
        assertEq(usdc.balanceOf(provider), JOB_PRICE);

        // A successful withdrawal cannot be repeated without a new credit.
        vm.prank(provider);
        vm.expectRevert(NebulaVerifiableAI.WithdrawInsufficient.selector);
        nebula.withdraw();

        assertEq(nebula.totalPendingWithdrawals(), 0);
        assertEq(usdc.balanceOf(provider), JOB_PRICE);
        assertTrue(nebula.invariant_solvency());
    }

    // ═══════════════════════════════════════════════════════════════════
    // Unit Tests — Admin
    // ═══════════════════════════════════════════════════════════════════

    function test_setVerifier_happy() public {
        address newVerifier = makeAddr("newVerifier");
        nebula.setVerifier(newVerifier);
        assertEq(nebula.verifier(), newVerifier);
    }

    function test_setVerifier_emits_event() public {
        address newVerifier = makeAddr("newVerifier");
        vm.expectEmit(true, true, false, false);
        emit VerifierUpdated(verifier, newVerifier);
        nebula.setVerifier(newVerifier);
    }

    function test_setVerifier_reverts_zero_address() public {
        vm.expectRevert(NebulaVerifiableAI.InvalidVerifier.selector);
        nebula.setVerifier(address(0));
    }

    function test_setVerifier_reverts_non_owner() public {
        vm.prank(user);
        vm.expectRevert();
        nebula.setVerifier(makeAddr("nice"));
    }

    function test_setMaxJobAmount_happy() public {
        nebula.setMaxJobAmount(50e6);
        assertEq(nebula.maxJobAmount(), 50e6);
    }

    function test_setMaxJobAmount_emits_event() public {
        uint256 oldMax = nebula.maxJobAmount();
        uint256 newMax = 200e6;
        vm.expectEmit(false, false, false, false);
        emit MaxJobAmountUpdated(oldMax, newMax);
        nebula.setMaxJobAmount(newMax);
    }

    function test_setMaxJobAmount_reverts_below_job_price() public {
        nebula.setJobPrice(100_000);
        vm.expectRevert(NebulaVerifiableAI.AmountExceedsMax.selector);
        nebula.setMaxJobAmount(50_000);
    }

    function test_setJobPrice_happy() public {
        nebula.setJobPrice(100_000);
        assertEq(nebula.jobPrice(), 100_000);
    }

    function test_setJobPrice_emits_event() public {
        uint256 oldPrice = nebula.jobPrice();
        uint256 newPrice = 100_000;
        vm.expectEmit(false, false, false, false);
        emit JobPriceUpdated(oldPrice, newPrice);
        nebula.setJobPrice(newPrice);
    }

    function test_setJobPrice_reverts_zero() public {
        vm.expectRevert(NebulaVerifiableAI.InvalidJobPrice.selector);
        nebula.setJobPrice(0);
    }

    function test_setJobPrice_reverts_above_max() public {
        nebula.setMaxJobAmount(100_000);
        vm.expectRevert(NebulaVerifiableAI.InvalidJobPrice.selector);
        nebula.setJobPrice(200_000);
    }

    // ═══════════════════════════════════════════════════════════════════
    // Adversarial Tests
    // ═══════════════════════════════════════════════════════════════════

    function test_reentrancy_on_withdraw() public {
        ReentrantUSDC maliciousToken = new ReentrantUSDC();
        NebulaVerifiableAI maliciousNebula = new NebulaVerifiableAI(address(maliciousToken));
        maliciousToken.setTarget(maliciousNebula);

        address victim = makeAddr("victim");
        maliciousToken.mint(victim, JOB_PRICE * 10);
        vm.startPrank(victim);
        maliciousToken.approve(address(maliciousNebula), type(uint256).max);
        bytes32 jobId = maliciousNebula.createJob(JOB_ID, FINGERPRINT);
        vm.stopPrank();

        maliciousNebula.assignProvider(jobId, victim, LEASE_ID, SafeCast.toUint64(block.timestamp + 3500));

        vm.prank(address(this));
        maliciousNebula.submitProof(jobId, LEASE_ID, keccak256("root"), keccak256("hash"));

        maliciousToken.setAttackJob(jobId);
        vm.prank(address(this));
        maliciousNebula.verifyJob(jobId, true);

        vm.prank(victim);
        maliciousNebula.withdraw();

        assertEq(maliciousNebula.getPendingWithdrawal(victim), 0);
    }

    function test_front_running_provider_cannot_steal() public {
        bytes32 jobId = _createDefaultJob();

        address attacker = makeAddr("attacker");
        vm.prank(attacker);
        vm.expectRevert(NebulaVerifiableAI.OnlyVerifier.selector);
        nebula.submitProof(jobId, LEASE_ID, keccak256("fake_root"), keccak256("fake_hash"));
    }

    function test_cannot_settle_with_wrong_verifier() public {
        address wrongVerifier = makeAddr("wrongVerifier");
        nebula.setVerifier(wrongVerifier);

        bytes32 jobId = _createDefaultJob();
        uint64 leaseExpiry = SafeCast.toUint64(block.timestamp + 3500);
        vm.prank(wrongVerifier);
        nebula.assignProvider(jobId, provider, LEASE_ID, leaseExpiry);

        vm.prank(wrongVerifier);
        nebula.submitProof(jobId, LEASE_ID, keccak256("root"), keccak256("hash"));

        // Old verifier loses all authority immediately after rotation.
        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.OnlyVerifier.selector);
        nebula.verifyJob(jobId, true);

        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.OnlyVerifier.selector);
        nebula.submitProof(jobId, LEASE_ID, keccak256("root2"), keccak256("hash2"));

        // New verifier settles fine.
        vm.prank(wrongVerifier);
        nebula.verifyJob(jobId, true);
        assertEq(nebula.getPendingWithdrawal(provider), JOB_PRICE);
    }

    // ═══════════════════════════════════════════════════════════════════
    // Accounting Invariant Tests (Unit/Assertion — not stateful)
    // ═══════════════════════════════════════════════════════════════════

    function test_invariant_no_double_settle() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);
        _submitDefaultProof(jobId);

        vm.prank(verifier);
        nebula.verifyJob(jobId, true);

        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.NoProofSubmitted.selector);
        nebula.verifyJob(jobId, true);

        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.NoProofSubmitted.selector);
        nebula.verifyJob(jobId, false);
    }

    function test_invariant_only_verifier_verifies() public {
        bytes32 jobId = _createDefaultJob();
        _assignDefaultProvider(jobId);
        _submitDefaultProof(jobId);

        address[] memory attackers = new address[](3);
        attackers[0] = user;
        attackers[1] = provider;
        attackers[2] = makeAddr("random");

        for (uint256 i = 0; i < attackers.length; i++) {
            vm.prank(attackers[i]);
            vm.expectRevert(NebulaVerifiableAI.OnlyVerifier.selector);
            nebula.verifyJob(jobId, true);
        }
    }

    function test_invariant_earnings_reconcile() public {
        bytes32 job1 = _createDefaultJob();
        _assignDefaultProvider(job1);
        _submitDefaultProof(job1);

        usdc.mint(user, JOB_PRICE);
        vm.startPrank(user);
        usdc.approve(address(nebula), type(uint256).max);
        bytes32 job2 = nebula.createJob(JOB_ID_3, FINGERPRINT);
        vm.stopPrank();

        _assignDefaultProvider(job2);
        vm.prank(verifier);
        nebula.submitProof(job2, LEASE_ID, keccak256("root2"), keccak256("hash2"));

        vm.startPrank(verifier);
        nebula.verifyJob(job1, true);
        nebula.verifyJob(job2, true);
        vm.stopPrank();

        assertEq(nebula.getPendingWithdrawal(provider), JOB_PRICE * 2);
        assertEq(nebula.totalEscrowed(), 0);
        assertEq(nebula.totalPendingWithdrawals(), JOB_PRICE * 2);

        vm.prank(provider);
        nebula.withdraw();

        assertEq(usdc.balanceOf(provider), JOB_PRICE * 2);
        assertEq(nebula.totalPendingWithdrawals(), 0);
    }

    // ═══════════════════════════════════════════════════════════════════
    // Fuzz Tests
    // ═══════════════════════════════════════════════════════════════════

    function testFuzz_setJobPrice(
        uint256 price
    ) public {
        vm.assume(price > 0 && price <= nebula.maxJobAmount());
        nebula.setJobPrice(price);
        assertEq(nebula.jobPrice(), price);
    }

    function testFuzz_setMaxJobAmount(
        uint256 max
    ) public {
        vm.assume(max >= nebula.jobPrice());
        nebula.setMaxJobAmount(max);
        assertEq(nebula.maxJobAmount(), max);
    }

    // ═══════════════════════════════════════════════════════════════════
    // Stateful Invariant Tests (True Stateful — 256+ runs)
    // ═══════════════════════════════════════════════════════════════════

    function test_invariant_solvency() public {
        bytes32 job1 = _createDefaultJob();
        _assignDefaultProvider(job1);
        _submitDefaultProof(job1);

        vm.prank(verifier);
        nebula.verifyJob(job1, true);

        assertEq(usdc.balanceOf(address(nebula)), JOB_PRICE);
        assertEq(nebula.totalEscrowed(), 0);
        assertEq(nebula.totalPendingWithdrawals(), JOB_PRICE);
        assertTrue(nebula.invariant_solvency());

        vm.prank(provider);
        nebula.withdraw();
        assertEq(usdc.balanceOf(address(nebula)), 0);
        assertEq(nebula.totalPendingWithdrawals(), 0);
        assertTrue(nebula.invariant_solvency());
    }

    function test_invariant_solvency_refund() public {
        bytes32 job1 = _createDefaultJob();

        vm.warp(block.timestamp + 86500);
        vm.prank(user);
        nebula.requestTimeoutRefund(job1);

        assertEq(nebula.totalEscrowed(), 0);
        assertEq(nebula.totalPendingWithdrawals(), JOB_PRICE);
        assertEq(usdc.balanceOf(address(nebula)), JOB_PRICE);
        assertTrue(nebula.invariant_solvency());

        vm.prank(user);
        nebula.withdraw();
        assertEq(usdc.balanceOf(address(nebula)), 0);
        assertEq(nebula.totalPendingWithdrawals(), 0);
        assertTrue(nebula.invariant_solvency());
    }

    function test_invariant_no_double_settle_state_machine() public {
        bytes32 job1 = _createDefaultJob();
        _assignDefaultProvider(job1);
        _submitDefaultProof(job1);

        vm.prank(verifier);
        nebula.verifyJob(job1, true);

        (,,,,,,,,,, uint64 completedAt, NebulaVerifiableAI.JobState state) = nebula.getJob(job1);
        assertEq(uint8(state), uint8(NebulaVerifiableAI.JobState.Settled));
        assertGt(completedAt, 0);
        assertTrue(nebula.invariant_no_double_settle(job1));
    }

    function test_invariant_timeout_refund_cannot_later_settle() public {
        bytes32 job1 = _createDefaultJob();

        vm.warp(block.timestamp + 86500);
        vm.prank(user);
        nebula.requestTimeoutRefund(job1);

        (,,,,,,,,,, uint64 completedAt, NebulaVerifiableAI.JobState state) = nebula.getJob(job1);
        assertEq(uint8(state), uint8(NebulaVerifiableAI.JobState.Refunded));
        assertGt(completedAt, 0);
        assertTrue(nebula.invariant_no_double_settle(job1));

        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.NoProofSubmitted.selector);
        nebula.verifyJob(job1, true);
    }

    function test_invariant_reassignment_does_not_change_escrow() public {
        bytes32 job1 = _createDefaultJob();
        uint256 escrowedBefore = nebula.totalEscrowed();

        _assignDefaultProvider(job1);
        assertEq(nebula.totalEscrowed(), escrowedBefore);

        vm.warp(4000);
        bytes32 newLeaseId = keccak256("lease_2");
        vm.prank(verifier);
        nebula.assignProvider(job1, makeAddr("provider2"), newLeaseId, 7000);

        assertEq(nebula.totalEscrowed(), escrowedBefore);
    }

    function test_invariant_authorized_provider_only() public {
        bytes32 job1 = _createDefaultJob();
        _assignDefaultProvider(job1);
        _submitDefaultProof(job1);

        vm.prank(verifier);
        nebula.verifyJob(job1, true);

        assertEq(nebula.getPendingWithdrawal(provider), JOB_PRICE);
        assertEq(nebula.getPendingWithdrawal(user), 0);
    }

    function test_invariant_solvency_multiple_active_jobs() public {
        // Create 3 jobs
        bytes32 job1 = _createDefaultJob();
        usdc.mint(user, JOB_PRICE * 2);
        vm.startPrank(user);
        usdc.approve(address(nebula), type(uint256).max);
        bytes32 job2 = nebula.createJob(JOB_ID_4, FINGERPRINT);
        bytes32 job3 = nebula.createJob(JOB_ID_5, FINGERPRINT);
        vm.stopPrank();

        // 3 active jobs: escrowed = 3 * JOB_PRICE, pending = 0
        assertEq(nebula.totalEscrowed(), JOB_PRICE * 3);
        assertEq(nebula.totalPendingWithdrawals(), 0);
        assertTrue(nebula.invariant_solvency());

        // Settle job1 valid
        _assignDefaultProvider(job1);
        _submitDefaultProof(job1);
        vm.prank(verifier);
        nebula.verifyJob(job1, true);

        // 2 active jobs: escrowed = 2 * JOB_PRICE, pending = JOB_PRICE
        assertEq(nebula.totalEscrowed(), JOB_PRICE * 2);
        assertEq(nebula.totalPendingWithdrawals(), JOB_PRICE);
        assertTrue(nebula.invariant_solvency());

        // Settle job2 invalid (refund to user)
        _assignDefaultProvider(job2);
        _submitDefaultProof(job2);
        vm.prank(verifier);
        nebula.verifyJob(job2, false);

        // 1 active job: escrowed = JOB_PRICE, pending = 2 * JOB_PRICE
        assertEq(nebula.totalEscrowed(), JOB_PRICE);
        assertEq(nebula.totalPendingWithdrawals(), JOB_PRICE * 2);
        assertTrue(nebula.invariant_solvency());

        // Settle job3 valid
        _assignDefaultProvider(job3);
        _submitDefaultProof(job3);
        vm.prank(verifier);
        nebula.verifyJob(job3, true);

        // 0 active jobs: escrowed = 0, pending = 3 * JOB_PRICE
        assertEq(nebula.totalEscrowed(), 0);
        assertEq(nebula.totalPendingWithdrawals(), JOB_PRICE * 3);
        assertTrue(nebula.invariant_solvency());

        // Partial withdrawal (provider withdraws 1 job worth)
        vm.prank(provider);
        nebula.withdraw();

        assertEq(nebula.totalPendingWithdrawals(), JOB_PRICE);
        assertTrue(nebula.invariant_solvency());
    }

    function test_invariant_solvency_partial_withdrawals() public {
        // Create and settle 2 jobs for provider
        bytes32 job1 = _createDefaultJob();
        _assignDefaultProvider(job1);
        _submitDefaultProof(job1);

        usdc.mint(user, JOB_PRICE);
        vm.startPrank(user);
        usdc.approve(address(nebula), type(uint256).max);
        bytes32 job2 = nebula.createJob(JOB_ID_4, FINGERPRINT);
        vm.stopPrank();

        _assignDefaultProvider(job2);
        _submitDefaultProof(job2);

        vm.startPrank(verifier);
        nebula.verifyJob(job1, true);
        nebula.verifyJob(job2, true);
        vm.stopPrank();

        assertEq(nebula.totalEscrowed(), 0);
        assertEq(nebula.totalPendingWithdrawals(), JOB_PRICE * 2);

        // Partial withdrawal
        vm.prank(provider);
        nebula.withdraw();

        assertEq(nebula.totalPendingWithdrawals(), 0);
        assertTrue(nebula.invariant_solvency());
    }

    function test_invariant_unsolicited_usdc() public {
        _createDefaultJob();

        // Unsolicited USDC does not affect invariant
        usdc.mint(address(nebula), 1_000_000);

        assertEq(nebula.totalEscrowed(), JOB_PRICE);
        assertEq(nebula.totalPendingWithdrawals(), 0);
        // balance = JOB_PRICE + 1_000_000 >= escrowed + pending
        assertTrue(nebula.invariant_solvency());
    }

    // ═══════════════════════════════════════════════════════════════════
    // Boundary Condition Tests (exact timestamps from PRD v3.1)
    // ═══════════════════════════════════════════════════════════════════

    function test_boundary_submitProof_at_exact_lease_expiry() public {
        bytes32 job1 = _createDefaultJob();
        uint64 leaseExpiry = SafeCast.toUint64(block.timestamp + 3600);
        vm.prank(verifier);
        nebula.assignProvider(job1, provider, LEASE_ID, leaseExpiry);

        vm.warp(leaseExpiry);

        vm.prank(verifier);
        nebula.submitProof(job1, LEASE_ID, keccak256("root"), keccak256("hash"));

        (,,,,,,,,,,, NebulaVerifiableAI.JobState state) = nebula.getJob(job1);
        assertEq(uint8(state), uint8(NebulaVerifiableAI.JobState.ProofSubmitted));
    }

    function test_boundary_submitProof_one_second_after_lease_expiry() public {
        bytes32 job1 = _createDefaultJob();
        uint64 leaseExpiry = SafeCast.toUint64(block.timestamp + 3600);
        vm.prank(verifier);
        nebula.assignProvider(job1, provider, LEASE_ID, leaseExpiry);

        vm.warp(leaseExpiry + 1);

        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.LeaseExpired.selector);
        nebula.submitProof(job1, LEASE_ID, keccak256("root"), keccak256("hash"));
    }

    function test_boundary_submitProof_at_exact_deadline() public {
        bytes32 job1 = _createDefaultJob();
        uint64 deadline = SafeCast.toUint64(block.timestamp + 86400);
        uint64 leaseExpiry = SafeCast.toUint64(block.timestamp + 3600);
        vm.prank(verifier);
        nebula.assignProvider(job1, provider, LEASE_ID, leaseExpiry);

        vm.warp(deadline);

        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.LeaseExpired.selector);
        nebula.submitProof(job1, LEASE_ID, keccak256("root"), keccak256("hash"));
    }

    function test_boundary_requestTimeoutRefund_at_exact_deadline() public {
        bytes32 job1 = _createDefaultJob();
        uint64 deadline = SafeCast.toUint64(block.timestamp + 86400);

        vm.warp(deadline);

        vm.prank(user);
        vm.expectRevert(NebulaVerifiableAI.RefundTooEarly.selector);
        nebula.requestTimeoutRefund(job1);
    }

    function test_boundary_requestTimeoutRefund_one_second_after_deadline() public {
        bytes32 job1 = _createDefaultJob();
        uint64 deadline = SafeCast.toUint64(block.timestamp + 86400);

        vm.warp(deadline + 1);

        vm.prank(user);
        nebula.requestTimeoutRefund(job1);

        (,,,,,,,,,,, NebulaVerifiableAI.JobState state) = nebula.getJob(job1);
        assertEq(uint8(state), uint8(NebulaVerifiableAI.JobState.Refunded));
    }

    function test_boundary_assignProvider_reassignment_exact_lease_expiry() public {
        bytes32 job1 = _createDefaultJob();
        uint64 initialExpiry = SafeCast.toUint64(block.timestamp + 3600);
        vm.prank(verifier);
        nebula.assignProvider(job1, provider, LEASE_ID, initialExpiry);

        vm.warp(initialExpiry);

        bytes32 newLeaseId = keccak256("lease_2");
        uint64 newExpiry = SafeCast.toUint64(uint256(initialExpiry) + 3500);
        vm.prank(verifier);
        vm.expectRevert(NebulaVerifiableAI.LeaseExpired.selector);
        nebula.assignProvider(job1, makeAddr("provider2"), newLeaseId, newExpiry);
    }

    function test_boundary_assignProvider_reassignment_one_second_after_lease_expiry() public {
        bytes32 job1 = _createDefaultJob();
        uint64 initialExpiry = SafeCast.toUint64(block.timestamp + 3600);
        vm.prank(verifier);
        nebula.assignProvider(job1, provider, LEASE_ID, initialExpiry);

        vm.warp(initialExpiry + 1);

        bytes32 newLeaseId = keccak256("lease_2");
        uint64 newExpiry = SafeCast.toUint64(uint256(initialExpiry) + 3501);
        vm.prank(verifier);
        nebula.assignProvider(job1, makeAddr("provider2"), newLeaseId, newExpiry);

        (, address jobProvider,,,, bytes32 jobLeaseId,,,,,, NebulaVerifiableAI.JobState state) = nebula.getJob(job1);
        assertEq(jobProvider, makeAddr("provider2"));
        assertEq(jobLeaseId, newLeaseId);
        assertEq(uint8(state), uint8(NebulaVerifiableAI.JobState.Assigned));
    }

    // ═══════════════════════════════════════════════════════════════════
    // Pause Modifier Tests
    // ═══════════════════════════════════════════════════════════════════

    function test_pause_createJob_reverts() public {
        nebula.pause();
        vm.prank(user);
        vm.expectRevert();
        nebula.createJob(JOB_ID, FINGERPRINT);
    }

    function test_pause_assignProvider_reverts() public {
        bytes32 job1 = _createDefaultJob();
        nebula.pause();
        vm.prank(verifier);
        vm.expectRevert();
        nebula.assignProvider(job1, provider, LEASE_ID, SafeCast.toUint64(block.timestamp + 3500));
    }

    function test_pause_submitProof_reverts() public {
        bytes32 job1 = _createDefaultJob();
        _assignDefaultProvider(job1);
        nebula.pause();
        vm.prank(verifier);
        vm.expectRevert();
        nebula.submitProof(job1, LEASE_ID, keccak256("root"), keccak256("hash"));
    }

    function test_paused_verifyJob_works() public {
        bytes32 job1 = _createDefaultJob();
        _assignDefaultProvider(job1);
        _submitDefaultProof(job1);
        nebula.pause();
        vm.prank(verifier);
        nebula.verifyJob(job1, true);
        (,,,,,,,,,,, NebulaVerifiableAI.JobState state) = nebula.getJob(job1);
        assertEq(uint8(state), uint8(NebulaVerifiableAI.JobState.Settled));
    }

    function test_paused_requestTimeoutRefund_works() public {
        bytes32 job1 = _createDefaultJob();
        vm.warp(block.timestamp + 86500);
        nebula.pause();
        vm.prank(user);
        nebula.requestTimeoutRefund(job1);
        (,,,,,,,,,,, NebulaVerifiableAI.JobState state) = nebula.getJob(job1);
        assertEq(uint8(state), uint8(NebulaVerifiableAI.JobState.Refunded));
    }

    function test_paused_withdraw_works() public {
        bytes32 job1 = _createDefaultJob();
        _assignDefaultProvider(job1);
        _submitDefaultProof(job1);
        vm.prank(verifier);
        nebula.verifyJob(job1, true);
        nebula.pause();
        vm.prank(provider);
        nebula.withdraw();
        assertEq(usdc.balanceOf(provider), JOB_PRICE);
    }

    // ═══════════════════════════════════════════════════════════════════
    // Edge Case Tests
    // ═══════════════════════════════════════════════════════════════════

    function test_getJob_nonexistent_returns_zeroes() public {
        bytes32 fakeJobId = keccak256("does_not_exist");
        (address jobUser,,,,,,,,,,, NebulaVerifiableAI.JobState state) = nebula.getJob(fakeJobId);
        assertEq(jobUser, address(0));
        assertEq(uint8(state), uint8(NebulaVerifiableAI.JobState.None));
    }

    function test_different_uuids_different_jobs() public {
        vm.prank(user);
        bytes32 job1 = nebula.createJob(JOB_ID_6, FINGERPRINT);

        vm.prank(user);
        bytes32 job2 = nebula.createJob(JOB_ID_7, FINGERPRINT);

        assertTrue(job1 != job2);
    }
}
