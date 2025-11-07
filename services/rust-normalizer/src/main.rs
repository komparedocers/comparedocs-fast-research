use anyhow::{Context, Result};
use lapin::{
    options::*, types::FieldTable, BasicProperties, Channel, Connection, ConnectionProperties,
};
use regex::Regex;
use serde::{Deserialize, Serialize};
use std::time::Instant;
use tracing::{error, info};
use unicode_normalization::UnicodeNormalization;

#[derive(Debug, Deserialize)]
struct Span {
    text: String,
    x: f32,
    y: f32,
    w: f32,
    h: f32,
    order: i32,
}

#[derive(Debug, Deserialize)]
struct PageExtractedMessage {
    doc_id: String,
    page_no: i32,
    json_uri: String,
    has_text_layer: bool,
    spans: Vec<Span>,
}

#[derive(Debug, Serialize, Clone)]
struct Chunk {
    id: String,
    text: String,
    page_no: i32,
    order: i32,
    char_count: usize,
}

#[derive(Debug, Serialize)]
struct PageChunkedMessage {
    doc_id: String,
    page_no: i32,
    chunks: Vec<Chunk>,
    chunk_uri: String,
}

struct Normalizer {
    channel: Channel,
    s3_client: aws_sdk_s3::Client,
    bucket_name: String,
    hyphen_regex: Regex,
    whitespace_regex: Regex,
}

impl Normalizer {
    async fn new(amqp_url: &str, s3_endpoint: &str, bucket_name: String) -> Result<Self> {
        let conn = Connection::connect(amqp_url, ConnectionProperties::default())
            .await
            .context("Failed to connect to RabbitMQ")?;

        let channel = conn.create_channel().await?;

        // Declare queues
        channel
            .queue_declare(
                "page.extracted",
                QueueDeclareOptions {
                    durable: true,
                    ..Default::default()
                },
                FieldTable::default(),
            )
            .await?;

        channel
            .queue_declare(
                "page.chunked",
                QueueDeclareOptions {
                    durable: true,
                    ..Default::default()
                },
                FieldTable::default(),
            )
            .await?;

        // Configure S3 client
        let config = aws_config::defaults(aws_config::BehaviorVersion::latest())
            .endpoint_url(s3_endpoint)
            .load()
            .await;
        let s3_client = aws_sdk_s3::Client::new(&config);

        Ok(Self {
            channel,
            s3_client,
            bucket_name,
            hyphen_regex: Regex::new(r"-\s*\n\s*").unwrap(),
            whitespace_regex: Regex::new(r"\s+").unwrap(),
        })
    }

    fn normalize_text(&self, text: &str) -> String {
        // Unicode normalization (NFKC)
        let normalized: String = text.nfkc().collect();

        // Fix line-break hyphens
        let dehyphenated = self.hyphen_regex.replace_all(&normalized, "");

        // Normalize whitespace
        let cleaned = self.whitespace_regex.replace_all(&dehyphenated, " ");

        cleaned.trim().to_string()
    }

    fn chunk_text(&self, spans: Vec<Span>, doc_id: &str, page_no: i32) -> Vec<Chunk> {
        let mut chunks = Vec::new();
        let mut current_paragraph = String::new();
        let mut chunk_order = 0;

        for (idx, span) in spans.iter().enumerate() {
            let normalized = self.normalize_text(&span.text);

            if normalized.is_empty() {
                continue;
            }

            // Simple paragraph detection: if we have accumulated text and hit a blank or short line
            let is_paragraph_break = current_paragraph.len() > 100
                && (normalized.len() < 20 || normalized.ends_with('.') || normalized.ends_with('!') || normalized.ends_with('?'));

            if is_paragraph_break {
                let chunk_id = format!("{}:{}:{}", doc_id, page_no, chunk_order);
                chunks.push(Chunk {
                    id: chunk_id,
                    text: current_paragraph.clone(),
                    page_no,
                    order: chunk_order,
                    char_count: current_paragraph.len(),
                });
                current_paragraph.clear();
                chunk_order += 1;
            }

            if !current_paragraph.is_empty() {
                current_paragraph.push(' ');
            }
            current_paragraph.push_str(&normalized);
        }

        // Add remaining text as final chunk
        if !current_paragraph.is_empty() {
            let chunk_id = format!("{}:{}:{}", doc_id, page_no, chunk_order);
            chunks.push(Chunk {
                id: chunk_id,
                text: current_paragraph,
                page_no,
                order: chunk_order,
                char_count: current_paragraph.len(),
            });
        }

        chunks
    }

    async fn upload_to_s3(&self, key: &str, data: &[u8]) -> Result<String> {
        self.s3_client
            .put_object()
            .bucket(&self.bucket_name)
            .key(key)
            .body(data.to_vec().into())
            .send()
            .await?;

        Ok(format!("s3://{}/{}", self.bucket_name, key))
    }

    async fn process_message(&self, msg: PageExtractedMessage) -> Result<()> {
        let start = Instant::now();
        info!("Normalizing page {} of doc {}", msg.page_no, msg.doc_id);

        // Chunk the text
        let chunks = self.chunk_text(msg.spans, &msg.doc_id, msg.page_no);

        // Store chunks
        let json_data = serde_json::to_vec(&chunks)?;
        let chunk_key = format!("chunks/{}/{}.json", msg.doc_id, msg.page_no);
        let chunk_uri = self.upload_to_s3(&chunk_key, &json_data).await?;

        // Publish chunked message
        let chunked_msg = PageChunkedMessage {
            doc_id: msg.doc_id,
            page_no: msg.page_no,
            chunks,
            chunk_uri,
        };

        let payload = serde_json::to_vec(&chunked_msg)?;

        self.channel
            .basic_publish(
                "",
                "page.chunked",
                BasicPublishOptions::default(),
                &payload,
                BasicProperties::default(),
            )
            .await?;

        let elapsed = start.elapsed();
        info!("Normalized and chunked page in {:?}", elapsed);
        Ok(())
    }

    async fn start(&self) -> Result<()> {
        info!("Starting normalizer worker...");

        let mut consumer = self
            .channel
            .basic_consume(
                "page.extracted",
                "normalizer-worker",
                BasicConsumeOptions::default(),
                FieldTable::default(),
            )
            .await?;

        while let Some(delivery) = consumer.next().await {
            if let Ok(delivery) = delivery {
                match serde_json::from_slice::<PageExtractedMessage>(&delivery.data) {
                    Ok(msg) => {
                        if let Err(e) = self.process_message(msg).await {
                            error!("Error processing message: {}", e);
                        }
                        delivery.ack(BasicAckOptions::default()).await?;
                    }
                    Err(e) => {
                        error!("Failed to deserialize message: {}", e);
                        delivery.nack(BasicNackOptions::default()).await?;
                    }
                }
            }
        }

        Ok(())
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();

    let amqp_url = std::env::var("BROKER_URL").unwrap_or_else(|_| "amqp://guest:guest@broker:5672".to_string());
    let s3_endpoint = std::env::var("S3_ENDPOINT").unwrap_or_else(|_| "http://minio:9000".to_string());
    let bucket_name = std::env::var("S3_BUCKET").unwrap_or_else(|_| "documents".to_string());

    info!("Connecting to broker at {}", amqp_url);
    let normalizer = Normalizer::new(&amqp_url, &s3_endpoint, bucket_name).await?;

    normalizer.start().await?;

    Ok(())
}
