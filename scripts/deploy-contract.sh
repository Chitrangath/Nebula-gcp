#!/bin/bash
# Deploy smart contract to Arbitrum Sepolia
set -e

echo "Deploying NebulaVerifiableAI to Arbitrum Sepolia..."

# Check required env vars
if [ -z "$DEPLOYER_KEY" ]; then
    echo "Error: DEPLOYER_KEY not set"
    exit 1
fi

if [ -z "$USDC_ADDRESS" ]; then
    echo "Error: USDC_ADDRESS not set"
    exit 1
fi

# Deploy
forge create src/NebulaVerifiableAI.sol:NebulaVerifiableAI \
    --rpc-url https://sepolia-rollup.arbitrum.io/rpc \
    --private-key $DEPLOYER_KEY \
    --constructor-args $USDC_ADDRESS \
    --verify

echo "Deployment complete!"
