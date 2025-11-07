# Deployment Guide

## Quick Deployment (Single Command)

The entire system can be deployed with a single command:

```bash
docker-compose up --build
```

This will:
1. Build all Rust services with release optimizations
2. Build all Python services
3. Build the React frontend
4. Initialize PostgreSQL with schema
5. Start RabbitMQ message broker
6. Start MinIO object storage
7. Start monitoring stack

## System Requirements

### Minimum Requirements
- **CPU**: 4 cores
- **RAM**: 8 GB
- **Disk**: 10 GB free space
- **OS**: Linux, macOS, or Windows with WSL2

### Recommended Requirements
- **CPU**: 8+ cores (for parallel processing)
- **RAM**: 16 GB (for concurrent document processing)
- **Disk**: 50 GB SSD/NVMe (for fast I/O)
- **OS**: Linux (best performance)

## Pre-Deployment Checklist

1. **Install Docker**:
   ```bash
   docker --version  # Should be 20.10+
   docker-compose --version  # Should be 2.0+
   ```

2. **Verify System Resources**:
   ```bash
   free -h  # Check available RAM
   df -h    # Check disk space
   ```

3. **Configure Firewall** (if needed):
   ```bash
   # Allow required ports
   sudo ufw allow 3000/tcp  # Frontend
   sudo ufw allow 8000/tcp  # Gateway API
   sudo ufw allow 9090/tcp  # Prometheus
   sudo ufw allow 3001/tcp  # Grafana
   ```

## Step-by-Step Deployment

### 1. Clone Repository

```bash
git clone <repository-url>
cd comparedocs-fast-research
```

### 2. Configure Environment

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` if you need custom configuration (optional for local deployment).

### 3. Build Services

Build all Docker images:

```bash
docker-compose build
```

Build times (approximate):
- Rust services: 5-10 minutes each (first build)
- Python services: 2-3 minutes each
- Frontend: 3-5 minutes
- Total: 20-30 minutes (first build with cold cache)

Subsequent builds are faster due to Docker layer caching.

### 4. Start Services

```bash
docker-compose up -d
```

Monitor startup logs:

```bash
docker-compose logs -f
```

Wait for all services to become healthy (1-2 minutes).

### 5. Verify Deployment

Check service health:

```bash
docker-compose ps
```

All services should show "healthy" status.

Test the API:

```bash
curl http://localhost:8000/health
# Should return: {"status":"healthy"}
```

Test the frontend:

```bash
curl http://localhost:3000
# Should return HTML
```

### 6. Access the System

Open your browser and navigate to:
- **Frontend**: http://localhost:3000
- **API Documentation**: http://localhost:8000/docs

## Service Startup Order

The docker-compose file ensures services start in the correct order:

1. **Infrastructure** (parallel):
   - PostgreSQL
   - Redis
   - RabbitMQ
   - MinIO

2. **Core Services** (after infrastructure):
   - Gateway API
   - Rust Extractor (3 replicas)
   - Rust Normalizer (2 replicas)
   - Rust Comparator
   - Embedder

3. **Frontend** (after gateway):
   - React application

4. **Monitoring** (parallel):
   - Prometheus
   - Grafana

## Scaling Services

### Horizontal Scaling

To scale worker services, edit `docker-compose.yml`:

```yaml
rust-extractor:
  deploy:
    replicas: 5  # Increase from 3 to 5
```

Then restart:

```bash
docker-compose up -d --scale rust-extractor=5
```

### Vertical Scaling

To allocate more resources to a service:

```yaml
gateway:
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 4G
      reservations:
        cpus: '1.0'
        memory: 2G
```

## Production Deployment

### Docker Swarm

1. Initialize swarm:
```bash
docker swarm init
```

2. Deploy stack:
```bash
docker stack deploy -c docker-compose.yml doccompare
```

3. Scale services:
```bash
docker service scale doccompare_rust-extractor=10
```

### Kubernetes

Convert docker-compose to Kubernetes manifests:

```bash
kompose convert -f docker-compose.yml
kubectl apply -f .
```

Or use Helm charts (recommended for production).

### Cloud Deployment

#### AWS
- Use ECS/Fargate for container orchestration
- RDS for PostgreSQL
- ElastiCache for Redis
- S3 for object storage
- SQS/EventBridge instead of RabbitMQ

#### GCP
- Use GKE for Kubernetes
- Cloud SQL for PostgreSQL
- Memorystore for Redis
- Cloud Storage for objects
- Pub/Sub for messaging

#### Azure
- Use AKS for Kubernetes
- Azure Database for PostgreSQL
- Azure Cache for Redis
- Blob Storage for objects
- Service Bus for messaging

## Security Hardening

### 1. Change Default Passwords

Edit `docker-compose.yml`:

```yaml
postgres:
  environment:
    POSTGRES_PASSWORD: <strong-password>

minio:
  environment:
    MINIO_ROOT_PASSWORD: <strong-password>

grafana:
  environment:
    GF_SECURITY_ADMIN_PASSWORD: <strong-password>
```

### 2. Enable TLS

Add SSL certificates and configure nginx:

```yaml
frontend:
  volumes:
    - ./certs:/etc/nginx/certs
```

### 3. Network Isolation

Create separate networks for different tiers:

```yaml
networks:
  frontend:
  backend:
  storage:
```

### 4. Resource Limits

Set limits for all services to prevent resource exhaustion:

```yaml
deploy:
  resources:
    limits:
      cpus: '1.0'
      memory: 1G
```

## Monitoring Setup

### Prometheus Metrics

Services expose metrics on `/metrics` endpoint.

View metrics:
```bash
curl http://localhost:8000/metrics
```

### Grafana Dashboards

1. Access Grafana: http://localhost:3001
2. Login: admin/admin
3. Import dashboards from `infra/grafana/dashboards/`

### Alerts

Configure alerts in Prometheus:

```yaml
# prometheus/alerts.yml
groups:
  - name: doccompare
    rules:
      - alert: HighQueueLag
        expr: rabbitmq_queue_messages > 1000
        for: 5m
```

## Backup and Recovery

### Database Backup

```bash
docker-compose exec postgres pg_dump -U postgres doccompare > backup.sql
```

### Restore Database

```bash
cat backup.sql | docker-compose exec -T postgres psql -U postgres doccompare
```

### Object Storage Backup

```bash
docker-compose exec minio mc mirror /data /backup
```

## Troubleshooting

### Service Won't Start

Check logs:
```bash
docker-compose logs [service-name]
```

### High Memory Usage

Reduce replicas:
```bash
docker-compose up -d --scale rust-extractor=1
```

### Slow Performance

1. Check queue depth in RabbitMQ
2. Monitor CPU/memory in Grafana
3. Scale up worker services
4. Check disk I/O (use SSD)

### Database Connection Issues

Verify PostgreSQL is healthy:
```bash
docker-compose exec postgres pg_isready
```

### Network Issues

Restart Docker networking:
```bash
docker-compose down
docker network prune
docker-compose up -d
```

## Maintenance

### Update Services

```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose up --build -d
```

### Clean Up

Remove old images:
```bash
docker image prune -a
```

Remove old volumes:
```bash
docker volume prune
```

### Log Rotation

Configure Docker log rotation in `/etc/docker/daemon.json`:

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

## Performance Tuning

### PostgreSQL

```sql
-- Increase shared buffers
ALTER SYSTEM SET shared_buffers = '4GB';

-- Increase work memory
ALTER SYSTEM SET work_mem = '256MB';

-- Reload configuration
SELECT pg_reload_conf();
```

### RabbitMQ

Increase message prefetch:
```bash
docker-compose exec broker rabbitmqctl set_policy prefetch ".*" '{"prefetch-count":100}' --apply-to queues
```

### MinIO

Enable caching:
```yaml
minio:
  environment:
    MINIO_CACHE_DRIVES: "/cache"
    MINIO_CACHE_QUOTA: 80
```

## Costs Estimation

### Cloud Costs (AWS, monthly)

- **Compute** (ECS Fargate):
  - 10 services × 1 vCPU × 2GB RAM × 730 hrs = ~$300
- **Database** (RDS PostgreSQL):
  - db.t3.medium = ~$70
- **Storage** (S3):
  - 1TB storage + requests = ~$25
- **Cache** (ElastiCache Redis):
  - cache.t3.small = ~$30
- **Message Queue** (SQS):
  - 10M requests = ~$5
- **Load Balancer** (ALB):
  - 1 ALB = ~$20

**Total**: ~$450/month for medium workload

### Bare Metal / VPS

- **VPS** (16 vCPU, 32GB RAM):
  - Hetzner AX101 = ~€100/month
  - Self-hosted, full control
  - No per-request costs

## Support

For deployment issues:
1. Check logs: `docker-compose logs`
2. Review documentation
3. Open GitHub issue
4. Contact support team
