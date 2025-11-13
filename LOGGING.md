# Comprehensive Logging Implementation

## Overview
Added comprehensive logging to all services for error tracing and debugging without breaking the system.

## Rust Services Logging

### Common Patterns Across All Rust Services
All Rust services (rust-comparator, rust-extractor, rust-normalizer, pdf-orchestrator) now include:

**Startup Logging:**
- `println!("=== SERVICE NAME STARTING ===")` - Immediate console output before logger init
- Configuration values (broker URL, S3 endpoint, bucket name)
- RabbitMQ connection establishment
- Channel creation
- Queue declarations
- S3 client initialization
- Service ready status

**Runtime Logging:**
- Message reception with document IDs and page numbers
- Processing start/end with timing information
- S3 operations (list, download, upload)
- Error conditions with full context
- Consumer loop lifecycle events

### rust-comparator (services/rust-comparator/src/main.rs)
**Logs:**
- Server binding to 0.0.0.0:8001
- S3 configuration (endpoint, bucket)
- Comparison requests (comparison ID, left/right doc IDs)
- Chunk loading from S3 (counts, file listings)
- JSON parsing operations
- Processing time per comparison

**Log Locations:**
- `main()`: Configuration and server startup
- `load_chunks()`: S3 list operations, downloads, JSON parsing
- `compare_documents()`: Comparison lifecycle

### rust-extractor (services/rust-extractor/src/main.rs)
**Logs:**
- RabbitMQ connection at startup
- Queue declarations (page.ready, page.extracted)
- Consumer subscription status
- Message reception per page
- PDF text extraction
- S3 uploads
- Processing time per page

**Log Locations:**
- `main()`: Configuration loading
- `new()`: Connection establishment, queue setup, S3 init
- `start()`: Consumer lifecycle
- Message processing loop

### rust-normalizer (services/rust-normalizer/src/main.rs)
**Logs:**
- RabbitMQ connection and queues (page.extracted, page.chunked)
- Message reception per page
- Text normalization and chunking
- S3 uploads of chunks
- Processing time

**Log Locations:**
- `main()`: Configuration loading
- `new()`: Connection establishment, queue setup, S3 init
- `start()`: Consumer lifecycle
- Message processing loop

### pdf-orchestrator (services/pdf-orchestrator/src/main.rs)
**Logs:**
- RabbitMQ connection and queues (ingest.pdf, page.ready)
- PDF ingestion messages
- Page count enumeration
- Fan-out of page.ready messages
- S3 downloads
- Processing time

**Log Locations:**
- `main()`: Configuration loading
- `new()`: Connection establishment, queue setup, S3 init
- `start()`: Consumer lifecycle
- `process_pdf()`: PDF processing and fan-out

## Python Gateway Logging

### services/gateway/main.py
**Already has 52+ log statements covering:**
- Startup configuration
- S3 bucket creation
- RabbitMQ connection pooling
- Document upload lifecycle:
  - File reception
  - SHA256 calculation
  - Duplicate detection
  - S3 upload
  - Database storage
  - Message publishing
- Comparison requests:
  - Request validation
  - Rust service calls
  - Response handling
  - Error conditions
- Health checks
- Configuration endpoints

**Log Levels:**
- INFO: Normal operations
- ERROR: Failures with full stack traces
- DEBUG: Detailed operation tracking

## Frontend Logging

### services/frontend/src/App.js
**Upload Function:**
- File details (name, size in MB, type)
- API URL being called
- Upload progress percentage
- Success/failure with detailed error messages
- Special handling for 413 (file too large) errors

**Comparison Function (Enhanced):**
- Document IDs being compared
- API endpoint
- Response data:
  - Comparison ID
  - Total matches count
  - Compliance statistics (count and percentage)
  - Non-compliance statistics
  - Processing time in milliseconds
- Error details:
  - HTTP status codes
  - Server error messages
  - User-friendly error descriptions
  - Special handling for 404 (documents not found) and 500 (server error)

**Console Output Format:**
```
=== UPLOAD START ===
File: document.pdf
Size: 2048 bytes (2.00 MB)
Type: application/pdf
API URL:
Upload URL: /upload
Upload progress: 50%
Upload response: {...}
=== UPLOAD SUCCESS ===
```

```
=== COMPARISON START ===
Left document ID: abc123
Right document ID: def456
API URL:
Compare URL: /compare
Sending comparison request...
Comparison response received:
- Comparison ID: xyz789
- Total matches: 45
- Compliant: 40 (88.89%)
- Non-compliant: 5 (11.11%)
- Processing time: 150 ms
=== COMPARISON SUCCESS ===
```

## Error Tracing Benefits

### Startup Issues
1. **Rust services exiting**: Can now see exactly where initialization fails
   - RabbitMQ connection errors
   - S3 client initialization failures
   - Queue declaration issues
   - Port binding conflicts

2. **Gateway failures**: Can trace:
   - Database connection issues
   - RabbitMQ connection problems
   - S3 bucket creation failures

### Runtime Issues
1. **Message flow**: Can track messages through the entire pipeline:
   - ingest.pdf → PDF Orchestrator
   - page.ready → Extractor
   - page.extracted → Normalizer
   - page.chunked → Embedder
   - Document IDs and page numbers at each stage

2. **S3 operations**: Can see:
   - Which files are being accessed
   - Upload/download success/failure
   - Bucket and key information
   - JSON parsing errors

3. **Comparison errors**: Can diagnose:
   - Missing documents
   - Empty chunk lists
   - S3 access issues
   - Processing timeouts

### Frontend Debugging
1. **Upload failures**: Clear indication of:
   - File size issues
   - Network errors
   - Server rejections
   - Configuration problems

2. **Comparison failures**: Detailed info on:
   - Which document IDs failed
   - Server-side errors
   - Processing status
   - Network issues

## Log Viewing

### Docker Logs
```bash
# View specific service logs
docker logs 1-comparedocs-fast-research-rust-comparator-1
docker logs 1-comparedocs-fast-research-gateway-1

# Follow logs in real-time
docker logs -f 1-comparedocs-fast-research-rust-comparator-1

# View logs from all Rust services
docker-compose logs rust-comparator rust-extractor rust-normalizer pdf-orchestrator

# View recent logs
docker-compose logs --tail=100 rust-comparator
```

### Browser Console
Open browser Developer Tools (F12) → Console tab to see:
- Upload progress and results
- Comparison requests and responses
- Error details
- API communication

## Log Levels (Rust)

Set via `RUST_LOG` environment variable (already configured in docker-compose.yml):
- `info`: Normal operation (default)
- `debug`: Detailed debugging
- `trace`: Very verbose

Example:
```yaml
environment:
  RUST_LOG: debug  # More verbose logging
```

## Summary

**Total Logging Coverage:**
- ✅ All Rust services: Comprehensive startup, runtime, and error logging
- ✅ Python Gateway: 52+ log statements covering all operations
- ✅ Frontend: Detailed console logging for user actions and errors
- ✅ All critical paths logged
- ✅ Error conditions logged with full context
- ✅ Performance metrics logged (processing times)
- ✅ No breaking changes - all existing functionality preserved

**Key Benefits:**
1. Can trace requests end-to-end through the system
2. Can identify exact point of failure
3. Can see timing information for performance analysis
4. Can debug production issues without code changes
5. Can correlate frontend actions with backend processing
