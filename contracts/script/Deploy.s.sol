// SPDX-License-Identifier: MIT
pragma solidity 0.8.20;

import {Script} from "forge-std/Script.sol";
import {DeploymentConfig} from "./DeploymentConfig.sol";
import {NebulaVerifiableAI} from "../src/NebulaVerifiableAI.sol";

/// @title Deploy
/// @notice Deploys and configures NebulaVerifiableAI from explicit environment configuration.
/// @dev Public configuration is validated before the deployer key is read or broadcast starts.
contract Deploy is Script {
    error UnsupportedNetwork(string network);
    error InvalidDeployerPrivateKey();
    error DeploymentAssertionFailed(bytes32 field);

    /// @notice Validate, deploy, configure, and verify a NebulaVerifiableAI instance.
    /// @dev Never logs or serializes the deployer private key.
    function run() external virtual returns (NebulaVerifiableAI deployed) {
        DeploymentConfig.Values memory values = _loadPublicConfiguration();
        DeploymentConfig.validate(values);

        uint256 deployerPrivateKey = vm.envUint("NEBULA_DEPLOYER_PRIVATE_KEY");
        deployed = _broadcastValidated(values, deployerPrivateKey);
    }

    function _broadcastValidated(
        DeploymentConfig.Values memory values,
        uint256 deployerPrivateKey
    ) internal returns (NebulaVerifiableAI deployed) {
        if (deployerPrivateKey == 0) revert InvalidDeployerPrivateKey();
        deployed = _broadcastValidatedWithKey(values, vm.addr(deployerPrivateKey), deployerPrivateKey);
    }

    function _broadcastValidatedFrom(
        DeploymentConfig.Values memory values,
        address deployer
    ) internal returns (NebulaVerifiableAI deployed) {
        vm.startBroadcast(deployer);
        deployed = _deployAndConfigure(values, deployer);
        vm.stopBroadcast();

        _assertConfiguration(deployed, values);
    }

    function _broadcastValidatedWithKey(
        DeploymentConfig.Values memory values,
        address deployer,
        uint256 deployerPrivateKey
    ) private returns (NebulaVerifiableAI deployed) {
        vm.startBroadcast(deployerPrivateKey);
        deployed = _deployAndConfigure(values, deployer);
        vm.stopBroadcast();

        _assertConfiguration(deployed, values);
    }

    function _loadPublicConfiguration() private view returns (DeploymentConfig.Values memory values) {
        values.network = _parseNetwork(vm.envString("NEBULA_DEPLOYMENT_NETWORK"));
        values.usdc = vm.envAddress("NEBULA_USDC");
        values.owner = vm.envAddress("NEBULA_CONTRACT_OWNER");
        values.verifier = vm.envAddress("NEBULA_BACKEND_VERIFIER");
        values.jobPrice = vm.envUint("NEBULA_JOB_PRICE");
        values.maxJobAmount = vm.envUint("NEBULA_MAX_JOB_AMOUNT");
    }

    function _parseNetwork(
        string memory rawNetwork
    ) internal pure returns (DeploymentConfig.NetworkMode) {
        bytes32 networkHash = keccak256(bytes(rawNetwork));
        if (networkHash == keccak256("local")) return DeploymentConfig.NetworkMode.Local;
        if (networkHash == keccak256("arbitrum-sepolia")) return DeploymentConfig.NetworkMode.ArbitrumSepolia;
        revert UnsupportedNetwork(rawNetwork);
    }

    function _deployAndConfigure(
        DeploymentConfig.Values memory values,
        address deployer
    ) private returns (NebulaVerifiableAI deployed) {
        deployed = new NebulaVerifiableAI(values.usdc);

        if (values.verifier != deployer) deployed.setVerifier(values.verifier);
        _configureEconomicBounds(deployed, values.jobPrice, values.maxJobAmount);

        if (values.owner != deployer) deployed.transferOwnership(values.owner);
    }

    function _configureEconomicBounds(
        NebulaVerifiableAI deployed,
        uint256 intendedPrice,
        uint256 intendedMaximum
    ) private {
        uint256 currentPrice = deployed.jobPrice();
        uint256 currentMaximum = deployed.maxJobAmount();

        if (intendedMaximum < currentPrice) {
            if (intendedPrice != currentPrice) deployed.setJobPrice(intendedPrice);
            if (intendedMaximum != currentMaximum) deployed.setMaxJobAmount(intendedMaximum);
        } else {
            if (intendedMaximum != currentMaximum) deployed.setMaxJobAmount(intendedMaximum);
            if (intendedPrice != currentPrice) deployed.setJobPrice(intendedPrice);
        }
    }

    function _assertConfiguration(
        NebulaVerifiableAI deployed,
        DeploymentConfig.Values memory values
    ) internal view {
        if (deployed.token() != values.usdc) revert DeploymentAssertionFailed("USDC");
        if (deployed.verifier() != values.verifier) revert DeploymentAssertionFailed("VERIFIER");
        if (deployed.owner() != values.owner) revert DeploymentAssertionFailed("OWNER");
        if (deployed.jobPrice() != values.jobPrice) revert DeploymentAssertionFailed("JOB_PRICE");
        if (deployed.maxJobAmount() != values.maxJobAmount) revert DeploymentAssertionFailed("MAX_JOB_AMOUNT");
        if (deployed.paused()) revert DeploymentAssertionFailed("PAUSED");
        if (deployed.totalEscrowed() != 0) revert DeploymentAssertionFailed("TOTAL_ESCROWED");
        if (deployed.totalPendingWithdrawals() != 0) revert DeploymentAssertionFailed("TOTAL_PENDING");
        if (!deployed.invariant_solvency()) revert DeploymentAssertionFailed("SOLVENCY");
    }
}
