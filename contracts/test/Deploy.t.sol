// SPDX-License-Identifier: MIT
pragma solidity 0.8.20;

import {Test} from "forge-std/Test.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Deploy} from "../script/Deploy.s.sol";
import {DeploymentConfig} from "../script/DeploymentConfig.sol";
import {NebulaVerifiableAI} from "../src/NebulaVerifiableAI.sol";

contract DeploymentUSDC is ERC20 {
    constructor() ERC20("Deployment USDC", "dUSDC") {}

    function decimals() public pure override returns (uint8) {
        return 6;
    }

    function mint(
        address recipient,
        uint256 amount
    ) external {
        _mint(recipient, amount);
    }
}

contract DeployHarness is Deploy {
    function deployValidated(
        DeploymentConfig.Values memory values,
        uint256 deployerPrivateKey
    ) external returns (NebulaVerifiableAI) {
        DeploymentConfig.validate(values);
        return _broadcastValidated(values, deployerPrivateKey);
    }

    function parseNetwork(
        string memory network
    ) external pure returns (DeploymentConfig.NetworkMode) {
        return _parseNetwork(network);
    }

    function assertConfiguration(
        NebulaVerifiableAI deployed,
        DeploymentConfig.Values memory values
    ) external view {
        _assertConfiguration(deployed, values);
    }
}

contract DeployTest is Test {
    uint256 private constant DEPLOYER_KEY = 0xD3_10;
    uint256 private constant DEFAULT_JOB_PRICE = 50_000;
    uint256 private constant DEFAULT_MAX_JOB_AMOUNT = 10_000_000;

    DeployHarness private deploymentScript;
    DeploymentUSDC private usdc;
    address private owner = makeAddr("contractOwner");
    address private verifier = makeAddr("backendVerifier");

    function setUp() public {
        deploymentScript = new DeployHarness();
        usdc = new DeploymentUSDC();
        vm.chainId(31_337);
    }

    function testDeploysAndConfiguresContractBeforeTransferringOwnership() public {
        NebulaVerifiableAI deployed = deploymentScript.deployValidated(_config(25_000, 5_000_000, owner), DEPLOYER_KEY);

        assertEq(deployed.token(), address(usdc));
        assertEq(deployed.verifier(), verifier);
        assertEq(deployed.owner(), owner);
        assertEq(deployed.jobPrice(), 25_000);
        assertEq(deployed.maxJobAmount(), 5_000_000);
        assertFalse(deployed.paused());
        assertEq(deployed.totalEscrowed(), 0);
        assertEq(deployed.totalPendingWithdrawals(), 0);
        assertTrue(deployed.invariant_solvency());

        vm.prank(vm.addr(DEPLOYER_KEY));
        vm.expectRevert(abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, vm.addr(DEPLOYER_KEY)));
        deployed.setVerifier(makeAddr("unauthorizedReplacement"));
    }

    function testKeepsDeployerAsOwnerWhenConfiguredOwnerMatches() public {
        address deployer = vm.addr(DEPLOYER_KEY);
        NebulaVerifiableAI deployed = deploymentScript.deployValidated(
            _config(DEFAULT_JOB_PRICE, DEFAULT_MAX_JOB_AMOUNT, deployer), DEPLOYER_KEY
        );

        assertEq(deployed.owner(), deployer);
        assertEq(deployed.verifier(), verifier);
    }

    function testConfiguresPriceBeforeLoweringMaximumBelowDefaultPrice() public {
        NebulaVerifiableAI deployed = deploymentScript.deployValidated(_config(10_000, 25_000, owner), DEPLOYER_KEY);

        assertEq(deployed.jobPrice(), 10_000);
        assertEq(deployed.maxJobAmount(), 25_000);
        assertEq(deployed.owner(), owner);
    }

    function testRaisesMaximumBeforeSettingPriceAboveDefaultMaximum() public {
        NebulaVerifiableAI deployed =
            deploymentScript.deployValidated(_config(20_000_000, 25_000_000, owner), DEPLOYER_KEY);

        assertEq(deployed.jobPrice(), 20_000_000);
        assertEq(deployed.maxJobAmount(), 25_000_000);
        assertEq(deployed.owner(), owner);
    }

    function testRunValidatesBeforeKeyParsingThenDeploysValidEnvironment() public {
        _setConfig(DEFAULT_JOB_PRICE, DEFAULT_MAX_JOB_AMOUNT, address(0));
        vm.setEnv("NEBULA_DEPLOYER_PRIVATE_KEY", "not-a-private-key");

        vm.expectRevert(DeploymentConfig.InvalidOwner.selector);
        deploymentScript.run();

        _setConfig(DEFAULT_JOB_PRICE, DEFAULT_MAX_JOB_AMOUNT, owner);
        vm.setEnv("NEBULA_DEPLOYER_PRIVATE_KEY", vm.toString(DEPLOYER_KEY));
        NebulaVerifiableAI deployed = deploymentScript.run();

        assertEq(deployed.owner(), owner);
        assertEq(deployed.verifier(), verifier);
    }

    function testRejectsUnsupportedNetwork() public {
        vm.expectRevert(abi.encodeWithSelector(Deploy.UnsupportedNetwork.selector, "mainnet"));
        deploymentScript.parseNetwork("mainnet");
    }

    function testParsesArbitrumSepoliaNetwork() public view {
        assertEq(
            uint256(deploymentScript.parseNetwork("arbitrum-sepolia")),
            uint256(DeploymentConfig.NetworkMode.ArbitrumSepolia)
        );
    }

    function testRejectsZeroDeployerPrivateKeyBeforeBroadcast() public {
        vm.expectRevert(Deploy.InvalidDeployerPrivateKey.selector);
        deploymentScript.deployValidated(_config(DEFAULT_JOB_PRICE, DEFAULT_MAX_JOB_AMOUNT, owner), 0);
    }

    function testPostDeploymentAssertionsRejectEveryReachableMismatch() public {
        DeploymentConfig.Values memory values = _config(DEFAULT_JOB_PRICE, DEFAULT_MAX_JOB_AMOUNT, address(this));
        NebulaVerifiableAI deployed = deploymentScript.deployValidated(values, DEPLOYER_KEY);

        DeploymentConfig.Values memory mismatched = _config(DEFAULT_JOB_PRICE, DEFAULT_MAX_JOB_AMOUNT, address(this));
        mismatched.usdc = makeAddr("wrongUSDC");
        _expectAssertionFailure(deployed, mismatched, "USDC");

        mismatched = _config(DEFAULT_JOB_PRICE, DEFAULT_MAX_JOB_AMOUNT, address(this));
        mismatched.verifier = makeAddr("wrongVerifier");
        _expectAssertionFailure(deployed, mismatched, "VERIFIER");

        mismatched = _config(DEFAULT_JOB_PRICE, DEFAULT_MAX_JOB_AMOUNT, address(this));
        mismatched.owner = makeAddr("wrongOwner");
        _expectAssertionFailure(deployed, mismatched, "OWNER");

        mismatched = _config(DEFAULT_JOB_PRICE, DEFAULT_MAX_JOB_AMOUNT, address(this));
        mismatched.jobPrice++;
        _expectAssertionFailure(deployed, mismatched, "JOB_PRICE");

        mismatched = _config(DEFAULT_JOB_PRICE, DEFAULT_MAX_JOB_AMOUNT, address(this));
        mismatched.maxJobAmount++;
        _expectAssertionFailure(deployed, mismatched, "MAX_JOB_AMOUNT");

        deployed.pause();
        _expectAssertionFailure(deployed, values, "PAUSED");
        deployed.unpause();

        address aiUser = makeAddr("aiUser");
        address provider = makeAddr("gpuProvider");
        bytes32 jobId = bytes32(uint256(1) << 128);
        bytes32 leaseId = keccak256("lease");
        usdc.mint(aiUser, DEFAULT_JOB_PRICE);
        vm.prank(aiUser);
        usdc.approve(address(deployed), DEFAULT_JOB_PRICE);
        vm.prank(aiUser);
        deployed.createJob(jobId, keccak256("fingerprint"));
        _expectAssertionFailure(deployed, values, "TOTAL_ESCROWED");

        vm.startPrank(verifier);
        deployed.assignProvider(jobId, provider, leaseId, uint64(block.timestamp + 1 hours));
        deployed.submitProof(jobId, leaseId, keccak256("merkleRoot"), keccak256("output"));
        deployed.verifyJob(jobId, true);
        vm.stopPrank();
        _expectAssertionFailure(deployed, values, "TOTAL_PENDING");

        vm.prank(provider);
        deployed.withdraw();
        deploymentScript.assertConfiguration(deployed, values);
    }

    function _setConfig(
        uint256 jobPrice,
        uint256 maxJobAmount,
        address configuredOwner
    ) private {
        vm.setEnv("NEBULA_DEPLOYMENT_NETWORK", "local");
        vm.setEnv("NEBULA_USDC", vm.toString(address(usdc)));
        vm.setEnv("NEBULA_CONTRACT_OWNER", vm.toString(configuredOwner));
        vm.setEnv("NEBULA_BACKEND_VERIFIER", vm.toString(verifier));
        vm.setEnv("NEBULA_JOB_PRICE", vm.toString(jobPrice));
        vm.setEnv("NEBULA_MAX_JOB_AMOUNT", vm.toString(maxJobAmount));
    }

    function _config(
        uint256 jobPrice,
        uint256 maxJobAmount,
        address configuredOwner
    ) private view returns (DeploymentConfig.Values memory) {
        return DeploymentConfig.Values({
            network: DeploymentConfig.NetworkMode.Local,
            usdc: address(usdc),
            owner: configuredOwner,
            verifier: verifier,
            jobPrice: jobPrice,
            maxJobAmount: maxJobAmount
        });
    }

    function _expectAssertionFailure(
        NebulaVerifiableAI deployed,
        DeploymentConfig.Values memory values,
        bytes32 field
    ) private {
        vm.expectRevert(abi.encodeWithSelector(Deploy.DeploymentAssertionFailed.selector, field));
        deploymentScript.assertConfiguration(deployed, values);
    }
}
