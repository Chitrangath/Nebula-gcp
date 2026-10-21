// SPDX-License-Identifier: MIT
pragma solidity 0.8.20;

import {IERC20Metadata} from "@openzeppelin/contracts/token/ERC20/extensions/IERC20Metadata.sol";

/// @title DeploymentConfig
/// @notice Validates public Nebula deployment parameters before a deployment script starts broadcasting.
/// @dev This library deliberately accepts no private key, worker signer, or GPU provider payout address.
library DeploymentConfig {
    uint256 internal constant LOCAL_CHAIN_ID = 31_337;
    uint256 internal constant ARBITRUM_SEPOLIA_CHAIN_ID = 421_614;
    uint8 internal constant USDC_DECIMALS = 6;

    enum NetworkMode {
        Unspecified,
        Local,
        ArbitrumSepolia
    }

    struct Values {
        NetworkMode network;
        address usdc;
        address owner;
        address verifier;
        uint256 jobPrice;
        uint256 maxJobAmount;
    }

    error InvalidNetworkMode();
    error UnexpectedChain(uint256 actualChainId, uint256 expectedChainId);
    error InvalidUSDC();
    error MissingUSDCCode(address usdc);
    error UnreadableUSDCDecimals(address usdc);
    error InvalidUSDCDecimals(uint256 actualDecimals);
    error InvalidOwner();
    error InvalidVerifier();
    error InvalidJobPrice(uint256 jobPrice, uint256 maxJobAmount);

    /// @notice Reverts unless all deployment parameters are safe for the selected network.
    /// @dev Must be called before `vm.startBroadcast` by every deployment entry point.
    function validate(
        Values memory values
    ) internal view {
        _validateNetwork(values.network);

        if (values.usdc == address(0)) revert InvalidUSDC();
        if (values.usdc.code.length == 0) revert MissingUSDCCode(values.usdc);

        (bool success, bytes memory returnData) = values.usdc.staticcall(abi.encodeCall(IERC20Metadata.decimals, ()));
        if (!success || returnData.length != 32) revert UnreadableUSDCDecimals(values.usdc);

        uint256 decodedDecimals = abi.decode(returnData, (uint256));
        if (decodedDecimals > type(uint8).max) revert UnreadableUSDCDecimals(values.usdc);
        if (decodedDecimals != USDC_DECIMALS) revert InvalidUSDCDecimals(decodedDecimals);

        if (values.owner == address(0)) revert InvalidOwner();
        if (values.verifier == address(0)) revert InvalidVerifier();
        if (values.jobPrice == 0 || values.jobPrice > values.maxJobAmount) {
            revert InvalidJobPrice(values.jobPrice, values.maxJobAmount);
        }
    }

    function _validateNetwork(
        NetworkMode network
    ) private view {
        uint256 expectedChainId;
        if (network == NetworkMode.Local) {
            expectedChainId = LOCAL_CHAIN_ID;
        } else if (network == NetworkMode.ArbitrumSepolia) {
            expectedChainId = ARBITRUM_SEPOLIA_CHAIN_ID;
        } else {
            revert InvalidNetworkMode();
        }

        if (block.chainid != expectedChainId) revert UnexpectedChain(block.chainid, expectedChainId);
    }
}
