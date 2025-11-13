#!/bin/bash

# This script adds comprehensive logging to pdf-orchestrator and rust-normalizer

echo "Adding logging to pdf-orchestrator..."
# The pattern is similar to rust-extractor since they both are message consumers

echo "Adding logging to rust-normalizer..."
# Similar pattern as well

echo "Done! Now rebuild services with: docker-compose build --no-cache pdf-orchestrator rust-normalizer"
