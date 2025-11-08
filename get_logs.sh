#!/bin/bash

echo "=== RUST COMPARATOR LOGS ==="
docker logs 1-comparedocs-fast-research-rust-comparator-1 2>&1

echo ""
echo "=== PDF ORCHESTRATOR LOGS ==="
docker logs 1-comparedocs-fast-research-pdf-orchestrator-1 2>&1

echo ""
echo "=== RUST EXTRACTOR LOGS ==="
docker logs 1-comparedocs-fast-research-rust-extractor-1 2>&1

echo ""
echo "=== RUST NORMALIZER LOGS ==="
docker logs 1-comparedocs-fast-research-rust-normalizer-1 2>&1

echo ""
echo "=== EMBEDDER LOGS ==="
docker logs 1-comparedocs-fast-research-embedder-1 2>&1
