.PHONY: help build up down logs clean test

help:
	@echo "DocCompare - Ultra-Fast Document Comparison System"
	@echo ""
	@echo "Available commands:"
	@echo "  make build    - Build all Docker images"
	@echo "  make up       - Start all services"
	@echo "  make down     - Stop all services"
	@echo "  make logs     - View logs from all services"
	@echo "  make clean    - Remove all containers, volumes, and images"
	@echo "  make restart  - Restart all services"
	@echo "  make status   - Show status of all services"
	@echo ""

build:
	@echo "Building all services..."
	docker-compose build

up:
	@echo "Starting all services..."
	docker-compose up -d
	@echo ""
	@echo "Services are starting up. Access points:"
	@echo "  Frontend:  http://localhost:3000"
	@echo "  API:       http://localhost:8000"
	@echo "  Grafana:   http://localhost:3001 (admin/admin)"
	@echo "  RabbitMQ:  http://localhost:15672 (guest/guest)"
	@echo "  MinIO:     http://localhost:9001 (minio/minio123)"
	@echo ""

down:
	@echo "Stopping all services..."
	docker-compose down

logs:
	docker-compose logs -f

clean:
	@echo "Cleaning up all containers, volumes, and images..."
	docker-compose down -v --rmi all
	@echo "Cleanup complete!"

restart:
	@echo "Restarting all services..."
	docker-compose restart

status:
	docker-compose ps

# Development helpers
dev-gateway:
	cd services/gateway && uvicorn main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd services/frontend && npm start

dev-rust-extractor:
	cd services/rust-extractor && cargo run

dev-rust-normalizer:
	cd services/rust-normalizer && cargo run

dev-rust-comparator:
	cd services/rust-comparator && cargo run
