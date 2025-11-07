# Rust+Python Ultra‑Fast Document Processing & Comparison Architecture (Dockerized)

> Goal: Process **thousands of PDFs per minute** (hundreds of pages each), extract/normalize content with **low-latency, low-RAM Rust** services, and run **AI‑based comparison & compliance** pipelines in **Python**. Everything is **containerized** and horizontally scalable.

---

## 1) High‑Level Overview

**Hot path (Rust)**
- **Ingress** → **PDF Inspector** → **Page Enumerator** → **Text Extractor** (PDFium) → **Light OCR Fallback** → **Normalizer** → **Chunker** → **Emitter** (page JSON + layout)

**AI path (Python)**
- **Embedding Service** (sentence/paragraph embeddings) → **Comparator** (semantic diff, rule checks) → **LLM Reasoner** (optional) → **Aggregator** (document‑level verdicts) → **Report Builder**

**Backbone**
- **Message broker** (Kafka or RabbitMQ)
- **Object storage** (S3/MinIO) for PDFs and page‑JSON artifacts
- **SQL (Postgres)** for metadata, jobs, lineage, audit
- **Redis** for hot caches and idempotency
- **Observability** (Prometheus, Grafana, Loki, Tempo/Jaeger, OpenTelemetry)

---

## 2) Data Flow (happy path)

1. **Upload**: Client posts PDF(s) → **Gateway API** stores binary in S3/MinIO; writes `documents` row (Postgres); emits `ingest.pdf` event with `{doc_id, s3_uri, sha256}`.
2. **Page Fan‑out**: **Rust PDF Orchestrator** streams PDF, enumerates pages, and emits one `page.ready` event per page `{doc_id, page_no, s3_uri, objects}`.
3. **Extraction**: **Rust Text Extractor** (PDFium) pulls `page.ready`, extracts text spans + bboxes + reading order; if text layer missing or tiny, emits `page.ocr.request`; else emits `page.extracted` with `{doc_id, page_no, spans[], images?}` and persists JSON to S3 `pages/<doc>/<page>.json`.
4. **OCR (rare)**: **Rust OCR Worker** (Leptonica+Tesseract via FFI or PaddleOCR via CUDA) performs region OCR → emits `page.extracted`.
5. **Normalize & Chunk**: **Rust Normalizer** standardizes unicode, hyphenation, ligatures, headers/footers removal; chunk into **semantic paragraphs** with stable IDs; stores `chunks/<doc>/<page>.json` and emits `page.chunked`.
6. **Embedding (Python)**: **Embedding Service** batches chunks for GPU/CPU models; persists vectors in **pgvector** or **Milvus/FAISS**; emits `page.embedded`.
7. **Comparison**: **Comparator Service** receives pair/workset `{left_doc_id, right_doc_id, strategy}`, fetches chunks/vectors, runs multi‑stage compare (fast hash → vector search → token/structure align) → emits `compare.done` with diff artifacts.
8. **LLM Reasoning (optional)**: For nuanced findings, **LLM Reasoner** reads candidate mismatches, produces explanations/justification → attaches citations (chunk IDs).
9. **Reporting**: **Report Builder** assembles **document‑level** report (JSON + HTML/PDF), stores to S3, updates `document_results`.

---

## 3) Core Services (with responsibilities)

### A) Gateway API (Python/FastAPI)
- Upload endpoints, presigned URLs, auth (JWT/OIDC), rate limiting.
- Idempotency on `sha256` to avoid re‑processing.
- Emits `ingest.pdf` to broker.

### B) Rust PDF Orchestrator
- Streams PDFs (range requests from S3), page enumeration.
- Lightweight structural scan (encryption, page count, embedded fonts/images summary).
- Emits per‑page jobs; maintains **job shards** for locality.

### C) Rust Text Extractor (PDFium bindings)
- Born‑digital text extraction with bboxes, fonts, reading order.
- Avoid rasterization; zero‑copy buffers where possible.
- Emits `page.extracted` and uploads compact JSON (≈ few 10s of KB/page).

### D) Rust OCR Worker (fallback only)
- Region detection (connected components + heuristic to skip pure‑text pages).
- DPI 150–200 for speed; deskew; multilingual packs on demand.
- Optional GPU OCR (PaddleOCR/TensorRT) if OCR rate > ~5%.

### E) Rust Normalizer & Chunker
- Unicode NFC/NFKC, ligature normalization, hyphen fix, paragraph segmentation.
- Header/footer detection via **repetition across pages**.
- Output: `Chunk{ id, page_no, text, bbox?, order_index }`.

### F) Embedding Service (Python)
- Models: `bge-large`, `E5`, or domain‑specific; multilingual variants for EU docs.
- Batching via **vLLM/TensorRT-LLM** or normal PyTorch on GPU; CPU fallback.
- Vector store: **pgvector** in Postgres for simplicity; Milvus if scale demands.

### G) Comparator Service (Python + Rust micro‑kernels)
- **Stage 1 (Rust):** Fast fingerprints → **SimHash/MinHash** per chunk to prune.
- **Stage 2 (Python):** Vector similarity (cosine) to propose candidate alignments.
- **Stage 3 (Rust):** Token‑level alignment (diff‑match‑patch or Myers O(ND)) with layout hints; sequence alignment (Needleman–Wunsch) across chunk streams.
- **Policies:** Exact match, near‑duplicate, paraphrase, insertion/deletion, reordering.

### H) Rule/Policy Engine (Python)
- Rules as **plain language → DSL** (YAML/JSON) or LLM‑assisted extraction.
- Deterministic validators (regex/AST for structured fields) and semantic checks (embedding+LLM) with **explanations and citations (chunk IDs)**.

### I) Report Builder (Python)
- Aggregates findings per rule/section; generates HTML/PDF with **click‑through to page/chunk**; redaction options.

---

## 4) Storage & Schemas

### S3/MinIO Layout
```
s3://bucket/
  pdfs/<sha256>.pdf
  pages/<doc_id>/<page_no>.json
  chunks/<doc_id>/<page_no>.json
  vectors/<doc_id>/<chunk_id>.npy (optional if not in DB)
  reports/<doc_id>/<run_id>.{json,html,pdf}
```

### Postgres (key tables)
- `documents(id, sha256, filename, size, page_count, created_at, status)`
- `pages(id, doc_id, page_no, status, s3_uri_json, has_text_layer)`
- `chunks(id, doc_id, page_no, order_index, text, bbox, hash_sim, created_at)`
- `embeddings(chunk_id, vector VECTOR(1024), model, normed bool)` (pgvector)
- `comparisons(id, left_doc_id, right_doc_id, strategy, created_at, status)`
- `matches(id, comparison_id, left_chunk_id, right_chunk_id, score, kind, evidence)`
- `rules(id, version, language, dsl jsonb)`
- `rule_results(id, comparison_id, rule_id, status, rationale, citations jsonb)`
- `jobs(id, kind, payload jsonb, state, retries, updated_at)`
- `audit(id, actor, action, object, ts, meta jsonb)`

Indexes: pgvector IVF/flat; B‑tree on `(doc_id, page_no)`, `(comparison_id)`.

---

## 5) Messaging (Kafka topics or RabbitMQ queues)
- `ingest.pdf` → PDF Orchestrator
- `page.ready` → Text Extractor
- `page.ocr.request` → OCR Worker
- `page.extracted` → Normalizer
- `page.chunked` → Embedding Service
- `page.embedded` → Comparator/Dispatcher
- `compare.request` → Comparator Service
- `compare.done` → Report Builder
- Dead‑letter queues for each stage

Message contract: Protobuf (preferred) for binary; JSON acceptable for control.

---

## 6) Performance Strategy
- **Page‑level parallelism**; avoid full‑PDF memory load; **range GET** from S3.
- **Buffer pooling** (Rust): `bytes::Bytes`, `mio`, or custom slab allocators.
- **OCR only on demand** with region pre‑filters.
- **Vectorization**: batch size tuned to GPU; pin memory for DMA.
- **Warm caches**: fonts map, rule sets, stopword sets in Redis.
- **Tail‑latency**: circuit‑break long pages; produce partials; retry with backoff.

Targets (indicative):
- Text extraction **1–5 ms/page** typical born‑digital on NVMe.
- Chunking/normalization < 1 ms/page.
- Embedding 1–3 ms/chunk @ A100; 5–10 ms/chunk @ CPU AVX512.
- Comparator end‑to‑end: **50–200 ms** for 100‑page vs 100‑page (after pruning), scalable with workers.

---

## 7) Security & Compliance
- **At rest**: S3 SSE‑KMS; Postgres TDE (if available) or disk LUKS; rotate keys.
- **In transit**: mTLS between services; OIDC for API; short‑lived presigned URLs.
- **PII**: field‑level redaction; access scopes by tenant; full audit trail.
- **Multitenancy**: `tenant_id` column on every table + RLS (Row Level Security).

---

## 8) Observability
- OpenTelemetry SDK (Rust & Python) → OTLP
- Prometheus metrics: per‑page latency, queue lag, OCR hit‑rate, GPU util
- Logs: Loki; Traces: Tempo/Jaeger; Dashboards: Grafana
- SLOs: p95 page extract < 8 ms; p99 compare job < 2 s

---

## 9) Docker Compose (production‑ish skeleton)

```yaml
version: "3.9"
services:
  gateway:
    image: app/gateway:latest
    build: ./services/gateway
    env_file: .env
    ports: ["8080:8080"]
    depends_on: [postgres, redis, minio, broker]

  rust-orchestrator:
    image: app/rust-orchestrator:latest
    build: ./services/rust-orchestrator
    env_file: .env
    depends_on: [minio, broker]

  rust-extractor:
    image: app/rust-extractor:latest
    build: ./services/rust-extractor
    env_file: .env
    deploy:
      replicas: 4
    depends_on: [minio, broker]

  rust-ocr:
    image: app/rust-ocr:latest
    build: ./services/rust-ocr
    env_file: .env
    deploy:
      replicas: 1
    # add GPU if using PaddleOCR/TensorRT
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - capabilities: [gpu]

  rust-normalizer:
    image: app/rust-normalizer:latest
    build: ./services/rust-normalizer
    env_file: .env

  embedder:
    image: app/embedder:latest
    build: ./services/embedder
    env_file: .env
    depends_on: [postgres]
    # optional GPU block similar to rust-ocr

  comparator:
    image: app/comparator:latest
    build: ./services/comparator
    env_file: .env
    depends_on: [postgres]

  report-builder:
    image: app/report-builder:latest
    build: ./services/report-builder
    env_file: .env

  broker:
    image: bitnami/kafka:latest  # or rabbitmq:3-management
    env_file: .env
    ports: ["9092:9092"]

  postgres:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: postgres
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports: ["5432:5432"]

  redis:
    image: redis:7
    ports: ["6379:6379"]

  minio:
    image: minio/minio:latest
    command: server /data --console-address :9001
    environment:
      MINIO_ROOT_USER: minio
      MINIO_ROOT_PASSWORD: minio123
    volumes:
      - minio:/data
    ports: ["9000:9000", "9001:9001"]

  grafana:
    image: grafana/grafana:latest
    ports: ["3000:3000"]

  prometheus:
    image: prom/prometheus:latest
    ports: ["9090:9090"]

volumes:
  pgdata: {}
  minio: {}
```

---

## 10) Service Interfaces (proto/HTTP)

### Ingest (Gateway → Broker)
```proto
message IngestPdf {
  string doc_id = 1;
  string tenant_id = 2;
  string s3_uri = 3;
  string sha256 = 4;
  string filename = 5;
}
```

### Page Event
```proto
message PageReady { string doc_id = 1; int32 page_no = 2; string s3_uri = 3; }
message PageExtracted {
  string doc_id = 1; int32 page_no = 2; string json_uri = 3;
  bool has_text_layer = 4; repeated Span spans = 5;
}
message Span { string text=1; float x=2; float y=3; float w=4; float h=5; int32 order=6; }
```

### Chunk & Embedding
```proto
message Chunked { string doc_id=1; int32 page_no=2; repeated Chunk chunks=3; }
message Chunk { string id=1; string text=2; optional BBox bbox=3; int32 order=4; }
message Embedding { string chunk_id=1; repeated float vector=2; string model=3; }
```

### Comparison Request
```proto
message CompareRequest {
  string comparison_id=1;
  string left_doc_id=2; string right_doc_id=3;
  string strategy=4; // exact|semantic|layout-aware|rules
  repeated string rule_ids=5;
}
```

---

## 11) Algorithms & Heuristics (Comparison)

**Pruning:**
- Length buckets; hash (SimHash/MinHash) on normalized shingles; discard far pairs.

**Candidate generation:**
- Top‑k vector neighbors (cosine) with pgvector IVF/flat index.

**Alignment:**
- Paragraph stream alignment with **Needleman–Wunsch** (affine gap) using vector sim as match score and layout penalties.
- Token‑level diff with Myers O(ND) or Google diff‑match‑patch; produce edit ops.

**Decision policy:**
- Threshold ladder: if hash≥t1 ⇒ exact; else if cos≥t2 ⇒ paraphrase; else if aligned gap>t3 ⇒ insertion/deletion.

**Rule checks:**
- Deterministic: regex/DSL.
- Semantic: prompt LLM with matched chunk pairs + citations.

---

## 12) Reliability & Ops
- **Exactly‑once semantics**: idempotency keys (`doc_id`, `page_no`, `stage`).
- **Retries**: exponential backoff per stage; DLQs with auto‑replay.
- **Shard‑aware consumers**: `hash(doc_id) % N` to keep page locality.
- **Blue/Green** deploys; config via env + Consul; feature flags.

---

## 13) Benchmarks Plan
- Synthetic corpus: born‑digital vs scanned; 1, 10, 100, 500 pages.
- KPIs: p50/p95 ms per page, OCR hit‑rate, GPU util, broker lag, RAM/worker.
- Load: Locust/K6 driving 5–20k pages/min; chaos tests (network jitter, S3 latency).

---

## 14) Security Model
- Multi‑tenant RLS in Postgres; per‑tenant buckets/prefixes in S3.
- mTLS service mesh (Linkerd/Istio optional) for zero‑trust internal calls.
- Audit every document access; immutable logs (WORM S3 bucket class).

---

## 15) Directory Layout (monorepo)
```
/infra
  docker-compose.yml
  grafana/ prometheus/
/services
  gateway/ (FastAPI)
  rust-orchestrator/
  rust-extractor/
  rust-ocr/
  rust-normalizer/
  embedder/ (FastAPI + models)
  comparator/ (FastAPI workers + rust kernels via pyo3)
  report-builder/
/libs
  proto/ (protobuf .proto, buf.build)
  rust-kernels/ (simhash, aligners)
  python-sdk/
/sql
  migrations/
/docs
  api.md  architecture.md  ops.md
```

---

## 16) Environment Variables (example)
- `S3_ENDPOINT, S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET`
- `BROKER_URL` (kafka or amqp)
- `DATABASE_URL` (postgres)
- `REDIS_URL`
- `OTEL_EXPORTER_OTLP_ENDPOINT`
- `EMBEDDING_MODEL_NAME`

---

## 17) Next Steps (Implementation Roadmap)
1. Scaffold repos & compose; wire basic ingest → page fan‑out → extract → store.
2. Add normalizer & chunker; design chunk schema + tests.
3. Stand up embedding service (CPU first), pgvector indices; e2e of small compare.
4. Implement pruning (SimHash) and alignment kernels (Rust, pyo3 bindings).
5. Add rules DSL + deterministic validators; minimal LLM reasoner.
6. Observability dashboards; load tests; SLOs + autoscaling thresholds.
7. Harden security (mTLS, RLS), audit, and multi‑tenant isolation.

---

**Result:** A production‑ready, horizontally scalable pipeline that hits **ms‑class per‑page** latency in the Rust hot path while keeping AI logic flexible in Python, all within a **clean Dockerized** architecture.

