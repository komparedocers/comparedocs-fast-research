#!/bin/bash

echo "Checking service status..."
echo ""

# Check which services are supposed to be running
services="broker postgres redis minio gateway pdf-orchestrator rust-extractor rust-normalizer rust-comparator embedder frontend"

for service in $services; do
    echo "Checking $service..."
done

echo ""
echo "Starting all services..."
echo ""

# Just restart everything to ensure all services are up
echo "This will stop and restart all services..."
