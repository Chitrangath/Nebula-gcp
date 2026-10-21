// SPDX-License-Identifier: MIT
pragma solidity 0.8.20;

import {Test} from "forge-std/Test.sol";
import {DeploymentConfig} from "../script/DeploymentConfig.sol";
import {Smoke} from "../script/Smoke.s.sol";

contract SmokeHarness is Smoke {
    function execute(
        SmokeIdentities memory identities
    ) external returns (SmokeResult memory) {
        return _runLocalSmoke(identities);
    }
}

contract SmokeTest is Test {
    SmokeHarness private smoke;

    function setUp() public {
        smoke = new SmokeHarness();
        vm.chainId(31_337);
    }

    function testRunsCompleteLocalLifecycleWithSeparatedIdentities() public {
        Smoke.SmokeIdentities memory identities = _distinctIdentities();

        Smoke.SmokeResult memory result = smoke.execute(identities);

        assertTrue(address(result.payment).code.length > 0);
        assertTrue(address(result.usdc).code.length > 0);
        assertEq(result.payment.owner(), identities.owner);
        assertEq(result.payment.verifier(), identities.verifier);
        assertEq(result.providerBalance, result.jobPrice);
        assertEq(result.aiUserBalance, result.jobPrice);
        assertEq(result.contractBalance, 0);
        assertTrue(result.payment.invariant_solvency());
    }

    function testRunLoadsNamedAnvilIdentitiesFromEnvironment() public {
        Smoke.SmokeIdentities memory identities = _distinctIdentities();
        vm.setEnv("ANVIL_DEPLOYER_ADDRESS", vm.toString(identities.deployer));
        vm.setEnv("ANVIL_OWNER_ADDRESS", vm.toString(identities.owner));
        vm.setEnv("ANVIL_VERIFIER_ADDRESS", vm.toString(identities.verifier));
        vm.setEnv("ANVIL_AI_USER_ADDRESS", vm.toString(identities.aiUser));
        vm.setEnv("ANVIL_PROVIDER_ADDRESS", vm.toString(identities.provider));
        vm.setEnv("ANVIL_WORKER_SIGNER_ADDRESS", vm.toString(identities.workerSigner));

        assertTrue(address(smoke.run()).code.length > 0);
    }

    function testRejectsZeroIdentity() public {
        Smoke.SmokeIdentities memory identities = _distinctIdentities();
        identities.workerSigner = address(0);

        vm.expectRevert(Smoke.InvalidSmokeIdentity.selector);
        smoke.execute(identities);
    }

    function testRejectsDuplicateIdentity() public {
        Smoke.SmokeIdentities memory identities = _distinctIdentities();
        identities.workerSigner = identities.provider;

        vm.expectRevert(Smoke.DuplicateSmokeIdentity.selector);
        smoke.execute(identities);
    }

    function testRejectsNonLocalChainBeforeDeployment() public {
        Smoke.SmokeIdentities memory identities = _distinctIdentities();
        vm.chainId(421_614);

        vm.expectRevert(abi.encodeWithSelector(DeploymentConfig.UnexpectedChain.selector, 421_614, 31_337));
        smoke.execute(identities);
    }

    function _distinctIdentities() private returns (Smoke.SmokeIdentities memory) {
        return Smoke.SmokeIdentities({
            deployer: makeAddr("deployer"),
            owner: makeAddr("owner"),
            verifier: makeAddr("verifier"),
            aiUser: makeAddr("aiUser"),
            provider: makeAddr("provider"),
            workerSigner: makeAddr("workerSigner")
        });
    }
}
