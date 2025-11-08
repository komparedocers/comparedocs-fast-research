# Document Anomaly Detection System - Debugging Session

## Problem Statement
All Rust worker services (rust-extractor, rust-normalizer, rust-comparator, pdf-orchestrator) were exiting immediately with code 0, preventing the document comparison pipeline from functioning.

## Root Causes Identified and Fixed

### 1. Missing `futures-util` Dependency
**Issue**: All Rust services using RabbitMQ consumers were missing the `futures-util` crate and `StreamExt` trait import.

**Impact**: Services couldn't use `.next()` on RabbitMQ consumers, causing compilation or runtime failures.

**Fix**: Added to all affected services:
- `futures-util = "0.3"` in Cargo.toml
- `use futures_util::StreamExt;` in main.rs

**Files Modified**:
- services/rust-extractor/Cargo.toml
- services/rust-extractor/src/main.rs
- services/rust-normalizer/Cargo.toml
- services/rust-normalizer/src/main.rs
- services/pdf-orchestrator/Cargo.toml
- services/pdf-orchestrator/src/main.rs

### 2. RabbitMQ Connection Being Dropped
**Issue**: The `Connection` object was created but not stored in the struct, causing Rust to immediately destroy it when it went out of scope. This closed all associated channels.

**Impact**: Consumer channels were invalid, causing services to exit immediately.

**Fix**: Added `_connection: Connection` field to each service struct and stored the connection:
```rust
struct Extractor {
    _connection: Connection,  // Added
    channel: Channel,
    s3_client: aws_sdk_s3::Client,
    bucket_name: String,
}

// In constructor:
Ok(Self {
    _connection: conn,  // Added
    channel,
    s3_client,
    bucket_name,
})
```

**Files Modified**:
- services/rust-extractor/src/main.rs
- services/rust-normalizer/src/main.rs
- services/pdf-orchestrator/src/main.rs

### 3. AWS S3 Client Configuration for MinIO
**Issue**: Using `aws_config::defaults()` which tries to load credentials from environment/IAM roles, incompatible with MinIO's static credentials.

**Impact**: S3 client initialization may have failed or used wrong credentials.

**Fix**: Changed to explicit credential configuration:
```rust
let credentials = aws_sdk_s3::config::Credentials::new(
    access_key,
    secret_key,
    None,
    None,
    "static",
);

let s3_config = aws_sdk_s3::config::Builder::new()
    .endpoint_url(&s3_endpoint)
    .credentials_provider(credentials)
    .region(aws_sdk_s3::config::Region::new("us-east-1"))
    .force_path_style(true)  // Required for MinIO
    .build();

let s3_client = aws_sdk_s3::Client::from_conf(s3_config);
```

**Files Modified**:
- services/rust-comparator/src/main.rs
- services/rust-extractor/src/main.rs
- services/rust-normalizer/src/main.rs
- services/pdf-orchestrator/src/main.rs

### 4. Missing `uuid` Dependency in rust-comparator
**Issue**: rust-comparator was using `uuid::Uuid::new_v4()` but uuid crate wasn't in Cargo.toml.

**Impact**: Service failed to compile or run.

**Fix**: Added `uuid = { version = "1", features = ["v4"] }` to Cargo.toml

**Files Modified**:
- services/rust-comparator/Cargo.toml

### 5. Python Embedder Version Incompatibility
**Issue**: `torch==2.1.2` and `sentence-transformers==2.3.1` had incompatible API changes.

**Error**: `AttributeError: module 'torch.utils._pytree' has no attribute 'register_pytree_node'`

**Fix**: Updated to compatible versions:
- `torch==2.3.0`
- `sentence-transformers==2.7.0`

**Files Modified**:
- services/embedder/requirements.txt

### 6. Missing Restart Policies
**Issue**: Docker was not configured to restart services if they exited, even with code 0.

**Impact**: Services that exit (even temporarily during startup issues) wouldn't automatically restart.

**Fix**: Added `restart: unless-stopped` to all Rust services in docker-compose.yml

**Files Modified**:
- docker-compose.yml

### 7. Added Debug Logging
**Issue**: No visibility into startup failures.

**Fix**: Added explicit println! statements before logger initialization:
```rust
#[tokio::main]
async fn main() -> Result<()> {
    println!("=== RUST COMPARATOR STARTING ===");

    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();

    info!("Rust comparator initializing...");
    // ... rest of code
}
```

**Files Modified**:
- services/rust-comparator/src/main.rs
- services/rust-extractor/src/main.rs
- services/rust-normalizer/src/main.rs
- services/pdf-orchestrator/src/main.rs

## Current Status

### Fixed Services
- ✅ embedder - Python version incompatibility resolved
- ✅ gateway - Working from the start
- ✅ frontend - Working from the start

### Pending Verification
- ⏳ rust-comparator - All fixes applied, needs restart to verify
- ⏳ rust-extractor - All fixes applied, needs restart to verify
- ⏳ rust-normalizer - All fixes applied, needs restart to verify
- ⏳ pdf-orchestrator - All fixes applied, needs restart to verify

## Next Steps

1. Restart all services with new configuration:
   ```bash
   docker-compose down
   docker-compose up -d
   ```

2. Verify Rust services are running:
   ```bash
   docker-compose ps | grep -E "(rust-|pdf-)"
   ```

3. Check logs for startup messages:
   ```bash
   docker logs 1-comparedocs-fast-research-rust-comparator-1
   docker logs 1-comparedocs-fast-research-pdf-orchestrator-1
   docker logs 1-comparedocs-fast-research-rust-extractor-1
   ```

4. If services are now running, test the full pipeline:
   - Upload a PDF via frontend at http://localhost:3000
   - Verify document processing
   - Test comparison functionality

## Technical Notes

### MinIO vs AWS S3
- MinIO requires `force_path_style(true)` configuration
- MinIO uses static credentials, not IAM roles
- Endpoint must be explicitly set

### RabbitMQ Consumer Pattern
- Connection must be kept alive by storing in struct
- Requires `futures_util::StreamExt` trait for `.next()` method
- Consumer loop blocks indefinitely waiting for messages

### Docker Restart Policies
- `restart: unless-stopped` - Always restart unless explicitly stopped
- Required for services that should run continuously
- Prevents issues where services exit on startup errors

## Debugging Tools Created

- `get_logs.sh` - Fetch logs from all Rust services
- `check_services.sh` - Check service status
- `diagnose.sh` - Run comprehensive diagnostics
- `rebuild_and_start.sh` - Full rebuild and restart
- `fix_and_restart.sh` - Comprehensive fix script
- `check_binaries.sh` - Verify binaries exist in containers

## Key Learnings

1. **Rust Ownership**: Unused values are dropped immediately - must store connections
2. **AWS SDK**: MinIO requires explicit configuration, can't use defaults
3. **Docker Logging**: No logs = binary not running, not just logger issue
4. **Restart Policies**: Critical for services that should run continuously
5. **Version Compatibility**: Python ML libraries have strict version requirements
