#!/bin/bash

echo "Checking if Rust binaries exist in containers..."

echo ""
echo "=== rust-comparator ==="
docker run --rm --entrypoint ls 1-comparedocs-fast-research-rust-comparator -la /usr/local/bin/ 2>&1 || echo "Container image not found or command failed"

echo ""
echo "=== pdf-orchestrator ==="
docker run --rm --entrypoint ls 1-comparedocs-fast-research-pdf-orchestrator -la /usr/local/bin/ 2>&1 || echo "Container image not found or command failed"

echo ""
echo "=== rust-extractor ==="
docker run --rm --entrypoint ls 1-comparedocs-fast-research-rust-extractor -la /usr/local/bin/ 2>&1 || echo "Container image not found or command failed"

echo ""
echo "Checking if we can run the binary directly..."
echo "=== Trying to run rust-comparator ==="
docker run --rm --entrypoint /usr/local/bin/rust-comparator 1-comparedocs-fast-research-rust-comparator 2>&1 | head -20
