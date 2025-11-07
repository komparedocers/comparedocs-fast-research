#!/bin/bash

set -e

echo "=== Stopping all services ==="
docker-compose down

echo ""
echo "=== Rebuilding Rust services (this will take a few minutes) ==="
docker-compose build --no-cache pdf-orchestrator rust-extractor rust-normalizer rust-comparator

echo ""
echo "=== Starting all services ==="
docker-compose up -d

echo ""
echo "=== Waiting 10 seconds for services to start ==="
sleep 10

echo ""
echo "=== Checking service status ==="
docker-compose ps

echo ""
echo "=== Checking if Rust services are running ==="
RUST_RUNNING=$(docker-compose ps | grep -E "(pdf-orchestrator|rust-extractor|rust-normalizer|rust-comparator)" | grep -c "Up" || true)
echo "Rust services running: $RUST_RUNNING"

if [ "$RUST_RUNNING" -gt 0 ]; then
    echo ""
    echo "✓ SUCCESS: Rust services are now running!"
    echo ""
    echo "To view logs, run: docker-compose logs -f rust-comparator"
else
    echo ""
    echo "✗ ERROR: Rust services still not running"
    echo ""
    echo "Checking logs for errors..."
    bash check_services.sh
fi
