#!/bin/bash

set -e

echo "=========================================="
echo "FIXING RUST SERVICES"
echo "=========================================="
echo ""

echo "Step 1: Verifying code fixes are in place..."
FIXES_OK=true

if ! grep -q "futures-util" services/rust-extractor/Cargo.toml; then
    echo "✗ ERROR: futures-util not found in rust-extractor/Cargo.toml"
    FIXES_OK=false
fi

if ! grep -q "futures-util" services/rust-normalizer/Cargo.toml; then
    echo "✗ ERROR: futures-util not found in rust-normalizer/Cargo.toml"
    FIXES_OK=false
fi

if ! grep -q "futures-util" services/pdf-orchestrator/Cargo.toml; then
    echo "✗ ERROR: futures-util not found in pdf-orchestrator/Cargo.toml"
    FIXES_OK=false
fi

if [ "$FIXES_OK" = true ]; then
    echo "✓ All code fixes verified"
else
    echo ""
    echo "ERROR: Code fixes not properly applied. Exiting."
    exit 1
fi

echo ""
echo "Step 2: Stopping all services..."
docker-compose down

echo ""
echo "Step 3: Removing old Rust service images to force full rebuild..."
docker-compose rm -f pdf-orchestrator rust-extractor rust-normalizer rust-comparator 2>/dev/null || true
docker images | grep -E "comparedocs-fast-research-(pdf-orchestrator|rust-extractor|rust-normalizer|rust-comparator)" | awk '{print $3}' | xargs -r docker rmi -f 2>/dev/null || true

echo ""
echo "Step 4: Building Rust services with --no-cache (this takes 3-5 minutes)..."
echo "Building pdf-orchestrator..."
docker-compose build --no-cache pdf-orchestrator

echo ""
echo "Building rust-extractor..."
docker-compose build --no-cache rust-extractor

echo ""
echo "Building rust-normalizer..."
docker-compose build --no-cache rust-normalizer

echo ""
echo "Building rust-comparator..."
docker-compose build --no-cache rust-comparator

echo ""
echo "Step 5: Starting all services..."
docker-compose up -d

echo ""
echo "Step 6: Waiting 15 seconds for services to initialize..."
sleep 15

echo ""
echo "Step 7: Checking service status..."
echo ""
docker-compose ps

echo ""
echo "Step 8: Checking if Rust services are running..."
RUST_UP=$(docker-compose ps | grep -E "(pdf-orchestrator|rust-extractor|rust-normalizer|rust-comparator)" | grep -c "Up" || echo "0")
RUST_TOTAL=$(docker-compose ps | grep -E "(pdf-orchestrator|rust-extractor|rust-normalizer|rust-comparator)" | wc -l)

echo "Rust services running: $RUST_UP out of $RUST_TOTAL"

if [ "$RUST_UP" -eq "$RUST_TOTAL" ] && [ "$RUST_UP" -gt 0 ]; then
    echo ""
    echo "=========================================="
    echo "✓ SUCCESS! All Rust services are running"
    echo "=========================================="
    echo ""
    echo "You can now test the application at http://localhost:3000"
    echo ""
    echo "To view logs:"
    echo "  docker-compose logs -f rust-comparator"
    echo "  docker-compose logs -f pdf-orchestrator"
    echo "  docker-compose logs -f gateway"
else
    echo ""
    echo "=========================================="
    echo "✗ FAILURE: Some Rust services are not running"
    echo "=========================================="
    echo ""
    echo "Checking logs for errors..."
    echo ""
    echo "--- PDF Orchestrator logs ---"
    docker-compose logs --tail=50 pdf-orchestrator
    echo ""
    echo "--- Rust Extractor logs ---"
    docker-compose logs --tail=50 rust-extractor | head -100
    echo ""
    echo "--- Rust Normalizer logs ---"
    docker-compose logs --tail=50 rust-normalizer | head -100
    echo ""
    echo "--- Rust Comparator logs ---"
    docker-compose logs --tail=50 rust-comparator
    exit 1
fi
