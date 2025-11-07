#!/bin/bash

echo "=== Checking Service Status ==="
docker-compose ps

echo ""
echo "=== Checking Rust Service Logs ==="

echo ""
echo "--- PDF Orchestrator Logs ---"
docker-compose logs --tail=50 pdf-orchestrator

echo ""
echo "--- Rust Extractor Logs ---"
docker-compose logs --tail=50 rust-extractor | head -100

echo ""
echo "--- Rust Normalizer Logs ---"
docker-compose logs --tail=50 rust-normalizer | head -100

echo ""
echo "--- Rust Comparator Logs ---"
docker-compose logs --tail=50 rust-comparator

echo ""
echo "--- Embedder Logs ---"
docker-compose logs --tail=50 embedder
