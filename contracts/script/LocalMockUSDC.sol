// SPDX-License-Identifier: MIT
pragma solidity 0.8.20;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

/// @title LocalMockUSDC
/// @notice Six-decimal mintable token for local Anvil deployment rehearsals only.
contract LocalMockUSDC is ERC20, Ownable {
    constructor(
        address initialOwner
    ) ERC20("Local Mock USDC", "mUSDC") Ownable(initialOwner) {}

    /// @notice Return USDC-compatible decimal precision for local validation.
    function decimals() public pure override returns (uint8) {
        return 6;
    }

    /// @notice Mint rehearsal funds; callable only by the local token owner.
    function mint(
        address recipient,
        uint256 amount
    ) external onlyOwner {
        _mint(recipient, amount);
    }
}
