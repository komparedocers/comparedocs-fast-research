#!/bin/bash

echo "=== DIAGNOSTIC SCRIPT FOR RUST SERVICES ==="
echo ""

echo "Step 1: Checking if fixes are in place..."
echo "Checking for futures-util in Cargo.toml files:"
echo ""

echo "rust-extractor:"
grep -n "futures-util" services/rust-extractor/Cargo.toml || echo "  ✗ NOT FOUND"

echo ""
echo "rust-normalizer:"
grep -n "futures-util" services/rust-normalizer/Cargo.toml || echo "  ✗ NOT FOUND"

echo ""
echo "pdf-orchestrator:"
grep -n "futures-util" services/pdf-orchestrator/Cargo.toml || echo "  ✗ NOT FOUND"

echo ""
echo "Checking for StreamExt import in source files:"
echo ""

echo "rust-extractor:"
grep -n "use futures_util::StreamExt" services/rust-extractor/src/main.rs || echo "  ✗ NOT FOUND"

echo ""
echo "rust-normalizer:"
grep -n "use futures_util::StreamExt" services/rust-normalizer/src/main.rs || echo "  ✗ NOT FOUND"

echo ""
echo "pdf-orchestrator:"
grep -n "use futures_util::StreamExt" services/pdf-orchestrator/src/main.rs || echo "  ✗ NOT FOUND"

echo ""
echo "================================================"
echo ""

echo "Step 2: Checking current service status..."
docker-compose ps | grep -E "(rust-|pdf-orchestrator|embedder)"

echo ""
echo "================================================"
echo ""

echo "Step 3: Getting last 30 lines of logs from each Rust service..."
echo ""

echo "--- PDF Orchestrator ---"
docker-compose logs --tail=30 pdf-orchestrator 2>&1

echo ""
echo "--- Rust Extractor (first replica) ---"
docker-compose logs --tail=30 rust-extractor 2>&1 | head -50

echo ""
echo "--- Rust Normalizer (first replica) ---"
docker-compose logs --tail=30 rust-normalizer 2>&1 | head -50

echo ""
echo "--- Rust Comparator ---"
docker-compose logs --tail=30 rust-comparator 2>&1

echo ""
echo "--- Embedder ---"
docker-compose logs --tail=30 embedder 2>&1

echo ""
echo "================================================"
echo ""
echo "DIAGNOSTIC COMPLETE"
echo ""
echo "Next steps:"
echo "1. If fixes are in place (futures-util found), rebuild images:"
echo "   docker-compose build --no-cache pdf-orchestrator rust-extractor rust-normalizer"
echo ""
echo "2. Then restart services:"
echo "   docker-compose up -d"
echo ""
echo "3. If fixes are NOT in place, there was a git issue. Check:"
echo "   git status"
