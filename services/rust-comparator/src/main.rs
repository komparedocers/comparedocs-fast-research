use anyhow::Result;
use axum::{
    extract::{Json, State},
    http::StatusCode,
    response::IntoResponse,
    routing::{get, post},
    Router,
};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use std::time::Instant;
use tracing::info;
use tower_http::cors::CorsLayer;

#[derive(Debug, Deserialize, Clone)]
struct Chunk {
    id: String,
    text: String,
    page_no: i32,
    order: i32,
    char_count: usize,
}

#[derive(Debug, Serialize, Deserialize)]
struct CompareRequest {
    left_doc_id: String,
    right_doc_id: String,
}

#[derive(Debug, Serialize)]
struct ChunkMatch {
    left_chunk_id: String,
    right_chunk_id: String,
    similarity_score: f64,
    match_type: String, // "exact", "similar", "paraphrase", "no_match"
    left_text: String,
    right_text: String,
    diff_html: String,
}

#[derive(Debug, Serialize)]
struct CompareResponse {
    comparison_id: String,
    left_doc_id: String,
    right_doc_id: String,
    matches: Vec<ChunkMatch>,
    compliant_count: usize,
    non_compliant_count: usize,
    compliant_percentage: f64,
    non_compliant_percentage: f64,
    processing_time_ms: u128,
    total_chunks_left: usize,
    total_chunks_right: usize,
}

struct AppState {
    s3_client: aws_sdk_s3::Client,
    bucket_name: String,
}

impl AppState {
    async fn download_from_s3(&self, key: &str) -> Result<Vec<u8>> {
        let resp = self.s3_client
            .get_object()
            .bucket(&self.bucket_name)
            .key(key)
            .send()
            .await?;

        let data = resp.body.collect().await?;
        Ok(data.into_bytes().to_vec())
    }

    async fn load_chunks(&self, doc_id: &str) -> Result<Vec<Chunk>> {
        let mut all_chunks = Vec::new();

        // Try to list all chunk files for this document
        let prefix = format!("chunks/{}/", doc_id);
        info!("Listing S3 objects with prefix: {} in bucket: {}", prefix, self.bucket_name);

        let objects = self.s3_client
            .list_objects_v2()
            .bucket(&self.bucket_name)
            .prefix(&prefix)
            .send()
            .await
            .map_err(|e| {
                tracing::error!("S3 list_objects_v2 failed for prefix {}: {}", prefix, e);
                anyhow::anyhow!("S3 list failed: {}", e)
            })?;

        if let Some(contents) = objects.contents {
            info!("Found {} chunk files in S3 for doc: {}", contents.len(), doc_id);
            for obj in contents {
                if let Some(key) = obj.key {
                    info!("Downloading chunk file: {}", key);
                    let data = self.download_from_s3(&key).await?;
                    let chunks: Vec<Chunk> = serde_json::from_slice(&data)
                        .map_err(|e| {
                            tracing::error!("Failed to parse JSON from {}: {}", key, e);
                            anyhow::anyhow!("JSON parse failed: {}", e)
                        })?;
                    info!("Loaded {} chunks from {}", chunks.len(), key);
                    all_chunks.extend(chunks);
                }
            }
        } else {
            tracing::warn!("No chunk files found in S3 for doc: {}", doc_id);
        }

        all_chunks.sort_by_key(|c| (c.page_no, c.order));
        info!("Total chunks loaded for {}: {}", doc_id, all_chunks.len());
        Ok(all_chunks)
    }

    fn compare_chunks(&self, left: &Chunk, right: &Chunk) -> ChunkMatch {
        let left_text = left.text.trim();
        let right_text = right.text.trim();

        // Calculate similarity using multiple metrics
        let jaro_sim = strsim::jaro_winkler(left_text, right_text);
        let normalized_levenshtein = strsim::normalized_levenshtein(left_text, right_text);

        // Average the scores
        let similarity_score = (jaro_sim + normalized_levenshtein) / 2.0;

        // Determine match type
        let match_type = if left_text == right_text {
            "exact"
        } else if similarity_score > 0.9 {
            "similar"
        } else if similarity_score > 0.7 {
            "paraphrase"
        } else {
            "no_match"
        };

        // Generate diff HTML
        let diff = similar::TextDiff::from_chars(left_text, right_text);
        let mut diff_html = String::new();
        for change in diff.iter_all_changes() {
            let sign = match change.tag() {
                similar::ChangeTag::Delete => format!("<span style='background-color: #ffcccc;'>{}</span>", change),
                similar::ChangeTag::Insert => format!("<span style='background-color: #ccffcc;'>{}</span>", change),
                similar::ChangeTag::Equal => change.to_string(),
            };
            diff_html.push_str(&sign);
        }

        ChunkMatch {
            left_chunk_id: left.id.clone(),
            right_chunk_id: right.id.clone(),
            similarity_score,
            match_type: match_type.to_string(),
            left_text: left_text.to_string(),
            right_text: right_text.to_string(),
            diff_html,
        }
    }

    async fn compare_documents(&self, req: CompareRequest) -> Result<CompareResponse> {
        let start = Instant::now();
        let comparison_id = uuid::Uuid::new_v4().to_string();

        info!("=== COMPARISON START === ID: {}, Left: {}, Right: {}",
            comparison_id, req.left_doc_id, req.right_doc_id);

        info!("Loading chunks from S3 for left document: {}", req.left_doc_id);
        let left_chunks = self.load_chunks(&req.left_doc_id).await
            .map_err(|e| {
                tracing::error!("Failed to load left document chunks: {}", e);
                e
            })?;

        info!("Loading chunks from S3 for right document: {}", req.right_doc_id);
        let right_chunks = self.load_chunks(&req.right_doc_id).await
            .map_err(|e| {
                tracing::error!("Failed to load right document chunks: {}", e);
                e
            })?;

        info!("✓ Loaded {} left chunks and {} right chunks", left_chunks.len(), right_chunks.len());

        let mut matches = Vec::new();

        // For simplicity, do a pairwise comparison
        // In production, use more sophisticated alignment algorithms
        let max_len = std::cmp::max(left_chunks.len(), right_chunks.len());

        for i in 0..max_len {
            if i < left_chunks.len() && i < right_chunks.len() {
                let chunk_match = self.compare_chunks(&left_chunks[i], &right_chunks[i]);
                matches.push(chunk_match);
            }
        }

        // Calculate compliance statistics
        let compliant_count = matches.iter()
            .filter(|m| m.match_type == "exact" || m.match_type == "similar")
            .count();

        let non_compliant_count = matches.len() - compliant_count;

        let total = matches.len() as f64;
        let compliant_percentage = if total > 0.0 {
            (compliant_count as f64 / total) * 100.0
        } else {
            0.0
        };

        let non_compliant_percentage = if total > 0.0 {
            (non_compliant_count as f64 / total) * 100.0
        } else {
            0.0
        };

        let processing_time_ms = start.elapsed().as_millis();

        Ok(CompareResponse {
            comparison_id,
            left_doc_id: req.left_doc_id,
            right_doc_id: req.right_doc_id,
            matches,
            compliant_count,
            non_compliant_count,
            compliant_percentage,
            non_compliant_percentage,
            processing_time_ms,
            total_chunks_left: left_chunks.len(),
            total_chunks_right: right_chunks.len(),
        })
    }
}

async fn health() -> impl IntoResponse {
    Json(serde_json::json!({ "status": "healthy" }))
}

async fn compare(
    State(state): State<Arc<AppState>>,
    Json(req): Json<CompareRequest>,
) -> Result<Json<CompareResponse>, (StatusCode, String)> {
    state.compare_documents(req)
        .await
        .map(Json)
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))
}

#[tokio::main]
async fn main() -> Result<()> {
    println!("=== RUST COMPARATOR STARTING ===");

    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();

    info!("Rust comparator initializing...");

    let s3_endpoint = std::env::var("S3_ENDPOINT")
        .unwrap_or_else(|_| "http://minio:9000".to_string());
    let bucket_name = std::env::var("S3_BUCKET")
        .unwrap_or_else(|_| "documents".to_string());
    let access_key = std::env::var("AWS_ACCESS_KEY_ID")
        .unwrap_or_else(|_| "minio".to_string());
    let secret_key = std::env::var("AWS_SECRET_ACCESS_KEY")
        .unwrap_or_else(|_| "minio123".to_string());

    info!("Configuration loaded - S3: {}, Bucket: {}", s3_endpoint, bucket_name);

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
        .force_path_style(true)
        .build();

    let s3_client = aws_sdk_s3::Client::from_conf(s3_config);
    info!("S3 client initialized successfully");

    let state = Arc::new(AppState {
        s3_client,
        bucket_name,
    });

    let app = Router::new()
        .route("/health", get(health))
        .route("/compare", post(compare))
        .layer(CorsLayer::permissive())
        .with_state(state);

    let addr = "0.0.0.0:8001";
    info!("Binding to address: {}", addr);

    let listener = tokio::net::TcpListener::bind(addr).await
        .map_err(|e| {
            tracing::error!("Failed to bind to {}: {}", addr, e);
            e
        })?;

    info!("✓ Rust comparator successfully started and listening on {}", addr);

    axum::serve(listener, app).await?;

    Ok(())
}
