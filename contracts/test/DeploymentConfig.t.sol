// SPDX-License-Identifier: MIT
pragma solidity 0.8.20;

import {Test} from "forge-std/Test.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {DeploymentConfig} from "../script/DeploymentConfig.sol";

contract SixDecimalToken is ERC20 {
    constructor() ERC20("Test USDC", "tUSDC") {}

    function decimals() public pure override returns (uint8) {
        return 6;
    }
}

contract EighteenDecimalToken is ERC20 {
    constructor() ERC20("Wrong Decimals", "WRONG") {}
}

contract RevertingDecimalsToken {
    function decimals() external pure returns (uint8) {
        revert("decimals unavailable");
    }
}

contract EmptyDecimalsReturnToken {
    fallback() external {}
}

contract InvalidDecimalsEncodingToken {
    fallback() external {
        assembly {
            mstore(0, 256)
            return(0, 32)
        }
    }
}

contract DeploymentConfigHarness {
    function validate(
        DeploymentConfig.Values memory values
    ) external view {
        DeploymentConfig.validate(values);
    }
}

contract DeploymentConfigTest is Test {
    uint256 private constant LOCAL_CHAIN_ID = 31_337;
    uint256 private constant ARBITRUM_SEPOLIA_CHAIN_ID = 421_614;

    DeploymentConfigHarness private validator;
    SixDecimalToken private usdc;

    address private owner = makeAddr("contractOwner");
    address private verifier = makeAddr("backendVerifier");

    function setUp() public {
        validator = new DeploymentConfigHarness();
        usdc = new SixDecimalToken();
        vm.chainId(LOCAL_CHAIN_ID);
    }

    function testAcceptsValidLocalConfiguration() public view {
        validator.validate(_validConfiguration(DeploymentConfig.NetworkMode.Local));
    }

    function testAcceptsValidArbitrumSepoliaConfiguration() public {
        vm.chainId(ARBITRUM_SEPOLIA_CHAIN_ID);
        validator.validate(_validConfiguration(DeploymentConfig.NetworkMode.ArbitrumSepolia));
    }

    function testRejectsUnspecifiedNetworkMode() public {
        DeploymentConfig.Values memory values = _validConfiguration(DeploymentConfig.NetworkMode.Local);
        values.network = DeploymentConfig.NetworkMode.Unspecified;

        vm.expectRevert(DeploymentConfig.InvalidNetworkMode.selector);
        validator.validate(values);
    }

    function testRejectsLocalModeOnWrongChain() public {
        vm.chainId(ARBITRUM_SEPOLIA_CHAIN_ID);

        vm.expectRevert(
            abi.encodeWithSelector(DeploymentConfig.UnexpectedChain.selector, ARBITRUM_SEPOLIA_CHAIN_ID, LOCAL_CHAIN_ID)
        );
        validator.validate(_validConfiguration(DeploymentConfig.NetworkMode.Local));
    }

    function testRejectsArbitrumSepoliaModeOnWrongChain() public {
        vm.expectRevert(
            abi.encodeWithSelector(DeploymentConfig.UnexpectedChain.selector, LOCAL_CHAIN_ID, ARBITRUM_SEPOLIA_CHAIN_ID)
        );
        validator.validate(_validConfiguration(DeploymentConfig.NetworkMode.ArbitrumSepolia));
    }

    function testRejectsZeroUSDCAddress() public {
        DeploymentConfig.Values memory values = _validConfiguration(DeploymentConfig.NetworkMode.Local);
        values.usdc = address(0);

        vm.expectRevert(DeploymentConfig.InvalidUSDC.selector);
        validator.validate(values);
    }

    function testRejectsUSDCAddressWithoutRuntimeCode() public {
        DeploymentConfig.Values memory values = _validConfiguration(DeploymentConfig.NetworkMode.Local);
        values.usdc = makeAddr("notAContract");

        vm.expectRevert(abi.encodeWithSelector(DeploymentConfig.MissingUSDCCode.selector, values.usdc));
        validator.validate(values);
    }

    function testRejectsUSDCWhenDecimalsCallReverts() public {
        RevertingDecimalsToken token = new RevertingDecimalsToken();
        DeploymentConfig.Values memory values = _validConfiguration(DeploymentConfig.NetworkMode.Local);
        values.usdc = address(token);

        vm.expectRevert(abi.encodeWithSelector(DeploymentConfig.UnreadableUSDCDecimals.selector, values.usdc));
        validator.validate(values);
    }

    function testRejectsUSDCWhenDecimalsReturnsNoData() public {
        EmptyDecimalsReturnToken token = new EmptyDecimalsReturnToken();
        DeploymentConfig.Values memory values = _validConfiguration(DeploymentConfig.NetworkMode.Local);
        values.usdc = address(token);

        vm.expectRevert(abi.encodeWithSelector(DeploymentConfig.UnreadableUSDCDecimals.selector, values.usdc));
        validator.validate(values);
    }

    function testRejectsUSDCWhenDecimalsEncodingIsInvalid() public {
        InvalidDecimalsEncodingToken token = new InvalidDecimalsEncodingToken();
        DeploymentConfig.Values memory values = _validConfiguration(DeploymentConfig.NetworkMode.Local);
        values.usdc = address(token);

        vm.expectRevert(abi.encodeWithSelector(DeploymentConfig.UnreadableUSDCDecimals.selector, values.usdc));
        validator.validate(values);
    }

    function testRejectsUSDCWithWrongDecimals() public {
        EighteenDecimalToken token = new EighteenDecimalToken();
        DeploymentConfig.Values memory values = _validConfiguration(DeploymentConfig.NetworkMode.Local);
        values.usdc = address(token);

        vm.expectRevert(abi.encodeWithSelector(DeploymentConfig.InvalidUSDCDecimals.selector, 18));
        validator.validate(values);
    }

    function testRejectsZeroOwnerAddress() public {
        DeploymentConfig.Values memory values = _validConfiguration(DeploymentConfig.NetworkMode.Local);
        values.owner = address(0);

        vm.expectRevert(DeploymentConfig.InvalidOwner.selector);
        validator.validate(values);
    }

    function testRejectsZeroVerifierAddress() public {
        DeploymentConfig.Values memory values = _validConfiguration(DeploymentConfig.NetworkMode.Local);
        values.verifier = address(0);

        vm.expectRevert(DeploymentConfig.InvalidVerifier.selector);
        validator.validate(values);
    }

    function testRejectsZeroJobPrice() public {
        DeploymentConfig.Values memory values = _validConfiguration(DeploymentConfig.NetworkMode.Local);
        values.jobPrice = 0;

        vm.expectRevert(abi.encodeWithSelector(DeploymentConfig.InvalidJobPrice.selector, 0, values.maxJobAmount));
        validator.validate(values);
    }

    function testRejectsJobPriceAboveMaximum() public {
        DeploymentConfig.Values memory values = _validConfiguration(DeploymentConfig.NetworkMode.Local);
        values.jobPrice = values.maxJobAmount + 1;

        vm.expectRevert(
            abi.encodeWithSelector(DeploymentConfig.InvalidJobPrice.selector, values.jobPrice, values.maxJobAmount)
        );
        validator.validate(values);
    }

    function testAcceptsJobPriceEqualToMaximum() public view {
        DeploymentConfig.Values memory values = _validConfiguration(DeploymentConfig.NetworkMode.Local);
        values.jobPrice = values.maxJobAmount;

        validator.validate(values);
    }

    function testFuzzAcceptsPositiveJobPriceAtOrBelowMaximum(
        uint128 rawPrice,
        uint128 rawMaximum
    ) public view {
        uint256 maximum = bound(uint256(rawMaximum), 1, type(uint128).max);
        uint256 price = bound(uint256(rawPrice), 1, maximum);
        DeploymentConfig.Values memory values = _validConfiguration(DeploymentConfig.NetworkMode.Local);
        values.jobPrice = price;
        values.maxJobAmount = maximum;

        validator.validate(values);
    }

    function testFuzzRejectsJobPriceAboveMaximum(
        uint128 rawMaximum,
        uint128 rawExcess
    ) public {
        uint256 maximum = uint256(rawMaximum);
        uint256 excess = bound(uint256(rawExcess), 1, type(uint128).max);
        uint256 price = maximum + excess;
        DeploymentConfig.Values memory values = _validConfiguration(DeploymentConfig.NetworkMode.Local);
        values.jobPrice = price;
        values.maxJobAmount = maximum;

        vm.expectRevert(abi.encodeWithSelector(DeploymentConfig.InvalidJobPrice.selector, price, maximum));
        validator.validate(values);
    }

    function _validConfiguration(
        DeploymentConfig.NetworkMode network
    ) private view returns (DeploymentConfig.Values memory) {
        return DeploymentConfig.Values({
            network: network,
            usdc: address(usdc),
            owner: owner,
            verifier: verifier,
            jobPrice: 50_000,
            maxJobAmount: 10e6
        });
    }
}
