# DocCompare - Ultra-Fast Document Anomaly Detection System

A high-performance document comparison and anomaly detection system built with Rust, Python, and React. Processes thousands of PDF documents per minute with results in seconds.

## Architecture

Based on the **Rust + Python Ultra-Fast Document Processing & Comparison Architecture**, this system combines:

- **Rust Services**: Ultra-fast PDF text extraction, normalization, and comparison
- **Python Services**: AI-powered embedding and semantic analysis
- **React Frontend**: Modern, responsive UI with real-time comparison results
- **PostgreSQL**: Robust data persistence
- **RabbitMQ**: Message-driven architecture for scalability
- **MinIO**: S3-compatible object storage
- **Prometheus + Grafana**: Real-time monitoring and observability

## Key Features

- ⚡ **Ultra-Fast Processing**: Process documents in milliseconds per page
- 📊 **Compliance Analysis**: Identify compliant and non-compliant paragraphs
- 🎯 **Anomaly Detection**: Detect differences, paraphrases, and structural changes
- 📈 **Performance Testing**: Built-in dashboard to test system throughput
- 🐳 **Fully Dockerized**: One command deployment with docker-compose
- 🔍 **Detailed Reports**: HTML diff view with similarity scores
- 📉 **Real-time Monitoring**: Prometheus metrics and Grafana dashboards

## System Components

### Rust Services (Performance-Critical Path)
1. **rust-extractor**: PDF text extraction using lopdf (1-5ms/page)
2. **rust-normalizer**: Text normalization and chunking (<1ms/page)
3. **rust-comparator**: Fast document comparison with multiple algorithms

### Python Services (AI Path)
1. **gateway**: FastAPI-based REST API and orchestration
2. **embedder**: Sentence embeddings for semantic comparison

### Frontend
- **React SPA**: Document upload, comparison UI, and performance testing dashboard

### Infrastructure
- **PostgreSQL**: Document metadata and comparison results
- **RabbitMQ**: Message queue for distributed processing
- **MinIO**: Object storage for PDFs and processed artifacts
- **Prometheus**: Metrics collection
- **Grafana**: Monitoring dashboards

## Quick Start

### Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- 8GB RAM minimum (16GB recommended)
- 10GB free disk space

### Deployment

1. **Clone the repository**:
```bash
git clone <repository-url>
cd comparedocs-fast-research
```

2. **Start all services**:
```bash
docker-compose up --build
```

This single command will:
- Build all Rust services (optimized release builds)
- Build all Python services
- Build the React frontend
- Start PostgreSQL with schema initialization
- Start RabbitMQ message broker
- Start MinIO object storage
- Start monitoring stack (Prometheus + Grafana)

3. **Access the services**:

- **Frontend UI**: http://localhost:3000
- **Gateway API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **RabbitMQ Management**: http://localhost:15672 (guest/guest)
- **MinIO Console**: http://localhost:9001 (minio/minio123)
- **Grafana**: http://localhost:3001 (admin/admin)
- **Prometheus**: http://localhost:9090

## Usage

### 1. Upload Documents

Use the frontend to upload two PDF documents:

1. Navigate to http://localhost:3000
2. Click "Document Comparison" tab
3. Upload a PDF as "Left Document"
4. Upload a PDF as "Right Document"
5. Click "Compare Documents"

### 2. View Comparison Results

The system will display:

- **Compliant Paragraphs**: Exact or similar matches
- **Non-Compliant Paragraphs**: Differences and anomalies
- **Compliance Percentages**: Visual breakdown
- **Processing Time**: Milliseconds to complete
- **Detailed Matches**: Side-by-side comparison with diff highlighting

### 3. Performance Testing

Use the built-in performance testing dashboard:

1. Click "Performance Testing" tab
2. Configure number of documents and concurrency
3. Click "Start Performance Test"
4. View real-time metrics:
   - Documents processed per second
   - Average upload time
   - Comparison time
   - Throughput statistics

## API Endpoints

### Upload Document
```bash
curl -X POST http://localhost:8000/upload \
  -F "file=@document.pdf"
```

### List Documents
```bash
curl http://localhost:8000/documents
```

### Compare Documents
```bash
curl -X POST http://localhost:8000/compare \
  -H "Content-Type: application/json" \
  -d '{
    "left_doc_id": "doc-id-1",
    "right_doc_id": "doc-id-2"
  }'
```

## Performance Benchmarks

Expected performance on modern hardware (16 cores, 32GB RAM, NVMe SSD):

- **Text Extraction**: 1-5 ms/page (born-digital PDFs)
- **Normalization**: <1 ms/page
- **Chunking**: <1 ms/page
- **Comparison**: 50-200 ms for 100-page vs 100-page documents
- **Throughput**: 1000+ pages/minute with 3 extractor replicas

## Architecture Highlights

### Message-Driven Processing

```
Upload → Gateway → page.ready → Extractor → page.extracted
                                              ↓
                                          Normalizer → page.chunked
                                                           ↓
                                                       Embedder
                                                           ↓
                                                      Comparator → Results
```

### Horizontal Scalability

The system uses Docker Compose `deploy.replicas` to scale critical services:

- **rust-extractor**: 3 replicas (CPU-bound)
- **rust-normalizer**: 2 replicas (CPU-bound)
- **embedder**: 1 replica (can be scaled for GPU)

To scale services, modify `docker-compose.yml`:

```yaml
deploy:
  replicas: 5  # Increase replicas
```

### Storage Layout

```
MinIO/S3:
  pdfs/{sha256}.pdf           - Original PDFs
  pages/{doc_id}/{page}.json  - Extracted text with spans
  chunks/{doc_id}/{page}.json - Normalized chunks
  reports/{doc_id}/{run}.html - Comparison reports
```

## Monitoring

Access Grafana at http://localhost:3001 to view:

- Document processing rate (pages/min)
- Queue lag and message throughput
- API latency (p50, p95, p99)
- Resource utilization (CPU, memory)
- Service health status

## Development

### Building Individual Services

**Rust services**:
```bash
cd services/rust-extractor
cargo build --release
```

**Python services**:
```bash
cd services/gateway
pip install -r requirements.txt
uvicorn main:app --reload
```

**Frontend**:
```bash
cd services/frontend
npm install
npm start
```

### Running Tests

Performance tests are built into the UI (Performance Testing tab).

## Troubleshooting

### Services not starting

Check logs:
```bash
docker-compose logs -f [service-name]
```

### High memory usage

Reduce extractor replicas:
```yaml
rust-extractor:
  deploy:
    replicas: 1  # Reduce from 3
```

### Slow processing

1. Check RabbitMQ queue depth at http://localhost:15672
2. Monitor Prometheus metrics at http://localhost:9090
3. Scale up critical services in docker-compose.yml

### Database connection errors

Ensure PostgreSQL is healthy:
```bash
docker-compose ps postgres
docker-compose logs postgres
```

## Production Considerations

For production deployment:

1. **Security**:
   - Change default passwords in docker-compose.yml
   - Enable TLS/SSL for all services
   - Implement authentication (JWT/OAuth)
   - Use secrets management (Vault, AWS Secrets Manager)

2. **Scalability**:
   - Use Kubernetes instead of docker-compose
   - Implement auto-scaling based on queue depth
   - Add GPU support for embedder service
   - Use managed services (RDS, ElastiCache, S3)

3. **Reliability**:
   - Implement circuit breakers
   - Add retry logic with exponential backoff
   - Set up dead-letter queues
   - Enable backup and disaster recovery

4. **Observability**:
   - Add distributed tracing (Jaeger/Tempo)
   - Implement structured logging (Loki)
   - Set up alerts (PagerDuty/Opsgenie)
   - Create SLOs and SLIs

## Technology Stack

- **Rust 1.75**: Systems programming, performance-critical paths
- **Python 3.11**: AI/ML, API orchestration
- **React 18**: Modern frontend with hooks
- **PostgreSQL 16**: Relational database
- **RabbitMQ 3**: Message broker
- **MinIO**: S3-compatible object storage
- **Prometheus**: Metrics and monitoring
- **Grafana**: Visualization and dashboards
- **Docker**: Containerization
- **Nginx**: Reverse proxy and static file serving

## License

MIT License - see LICENSE file for details

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Support

For issues and questions:
- Open an issue on GitHub
- Check existing documentation
- Review architecture.md for design details

---

**Built for Speed. Designed for Scale.**
