use anyhow::{Context, Result};
use futures_util::StreamExt;
use lapin::{
    options::*, types::FieldTable, BasicProperties, Channel, Connection, ConnectionProperties,
};
use serde::{Deserialize, Serialize};
use std::time::Instant;
use tracing::{error, info};

#[derive(Debug, Deserialize, Serialize)]
struct PageReadyMessage {
    doc_id: String,
    page_no: i32,
    s3_uri: String,
    sha256: String,
}

#[derive(Debug, Serialize)]
struct Span {
    text: String,
    x: f32,
    y: f32,
    w: f32,
    h: f32,
    order: i32,
}

#[derive(Debug, Serialize)]
struct PageExtractedMessage {
    doc_id: String,
    page_no: i32,
    json_uri: String,
    has_text_layer: bool,
    spans: Vec<Span>,
    extracted_at: String,
}

struct Extractor {
    _connection: Connection,
    channel: Channel,
    s3_client: aws_sdk_s3::Client,
    bucket_name: String,
}

impl Extractor {
    async fn new(amqp_url: &str, s3_endpoint: &str, bucket_name: String) -> Result<Self> {
        info!("Connecting to RabbitMQ at: {}", amqp_url);
        let conn = Connection::connect(amqp_url, ConnectionProperties::default())
            .await
            .context("Failed to connect to RabbitMQ")?;
        info!("✓ RabbitMQ connection established");

        let channel = conn.create_channel().await?;
        info!("✓ RabbitMQ channel created");

        // Declare queues
        info!("Declaring queue: page.ready");
        channel
            .queue_declare(
                "page.ready",
                QueueDeclareOptions {
                    durable: true,
                    ..Default::default()
                },
                FieldTable::default(),
            )
            .await?;

        info!("Declaring queue: page.extracted");
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
        info!("✓ Queues declared successfully");

        // Configure S3 client
        let access_key = std::env::var("AWS_ACCESS_KEY_ID").unwrap_or_else(|_| "minio".to_string());
        let secret_key = std::env::var("AWS_SECRET_ACCESS_KEY").unwrap_or_else(|_| "minio123".to_string());

        info!("Initializing S3 client for endpoint: {}", s3_endpoint);
        let credentials = aws_sdk_s3::config::Credentials::new(
            access_key,
            secret_key,
            None,
            None,
            "static",
        );

        let s3_config = aws_sdk_s3::config::Builder::new()
            .endpoint_url(s3_endpoint)
            .credentials_provider(credentials)
            .region(aws_sdk_s3::config::Region::new("us-east-1"))
            .force_path_style(true)
            .build();

        let s3_client = aws_sdk_s3::Client::from_conf(s3_config);
        info!("✓ S3 client initialized");

        Ok(Self {
            _connection: conn,
            channel,
            s3_client,
            bucket_name,
        })
    }

    async fn extract_text_from_pdf(&self, pdf_bytes: &[u8]) -> Result<Vec<Span>> {
        let start = Instant::now();
        let mut spans = Vec::new();

        // Use lopdf for fast extraction
        let doc = lopdf::Document::load_mem(pdf_bytes)?;

        let pages = doc.get_pages();
        for (page_num, page_id) in pages.iter().enumerate() {
            if let Ok(text) = doc.extract_text(&[*page_id]) {
                // Split into lines and create spans
                for (idx, line) in text.lines().enumerate() {
                    if !line.trim().is_empty() {
                        spans.push(Span {
                            text: line.to_string(),
                            x: 0.0,
                            y: idx as f32 * 12.0,
                            w: line.len() as f32 * 6.0,
                            h: 12.0,
                            order: idx as i32,
                        });
                    }
                }
            }
        }

        let elapsed = start.elapsed();
        info!("Extracted {} spans in {:?}", spans.len(), elapsed);
        Ok(spans)
    }

    async fn download_from_s3(&self, s3_uri: &str) -> Result<Vec<u8>> {
        let key = s3_uri.trim_start_matches("s3://").trim_start_matches(&format!("{}/", self.bucket_name));

        let resp = self.s3_client
            .get_object()
            .bucket(&self.bucket_name)
            .key(key)
            .send()
            .await?;

        let data = resp.body.collect().await?;
        Ok(data.into_bytes().to_vec())
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

    async fn process_message(&self, msg: PageReadyMessage) -> Result<()> {
        let start = Instant::now();
        info!("Processing page {} of doc {}", msg.page_no, msg.doc_id);

        // Download PDF from S3
        let pdf_bytes = self.download_from_s3(&msg.s3_uri).await?;

        // Extract text
        let spans = self.extract_text_from_pdf(&pdf_bytes).await?;

        // Store extracted data
        let json_data = serde_json::to_vec(&spans)?;
        let json_key = format!("pages/{}/{}.json", msg.doc_id, msg.page_no);
        let json_uri = self.upload_to_s3(&json_key, &json_data).await?;

        // Publish extracted message
        let extracted_msg = PageExtractedMessage {
            doc_id: msg.doc_id,
            page_no: msg.page_no,
            json_uri,
            has_text_layer: !spans.is_empty(),
            spans,
            extracted_at: chrono::Utc::now().to_rfc3339(),
        };

        let payload = serde_json::to_vec(&extracted_msg)?;

        self.channel
            .basic_publish(
                "",
                "page.extracted",
                BasicPublishOptions::default(),
                &payload,
                BasicProperties::default(),
            )
            .await?;

        let elapsed = start.elapsed();
        info!("Processed page in {:?}", elapsed);
        Ok(())
    }

    async fn start(&self) -> Result<()> {
        info!("Starting extractor worker, subscribing to queue: page.ready");

        let mut consumer = self
            .channel
            .basic_consume(
                "page.ready",
                "extractor-worker",
                BasicConsumeOptions::default(),
                FieldTable::default(),
            )
            .await
            .map_err(|e| {
                tracing::error!("Failed to start consumer: {}", e);
                e
            })?;

        info!("✓ Extractor worker ready and waiting for messages on queue 'page.ready'");

        while let Some(delivery) = consumer.next().await {
            if let Ok(delivery) = delivery {
                match serde_json::from_slice::<PageReadyMessage>(&delivery.data) {
                    Ok(msg) => {
                        info!("Received page.ready message for doc: {}, page: {}", msg.doc_id, msg.page_no);
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

        tracing::warn!("Consumer loop ended unexpectedly");
        Ok(())
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    println!("=== RUST EXTRACTOR STARTING ===");

    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();

    info!("Rust extractor initializing...");

    let amqp_url = std::env::var("BROKER_URL").unwrap_or_else(|_| "amqp://guest:guest@broker:5672".to_string());
    let s3_endpoint = std::env::var("S3_ENDPOINT").unwrap_or_else(|_| "http://minio:9000".to_string());
    let bucket_name = std::env::var("S3_BUCKET").unwrap_or_else(|_| "documents".to_string());

    info!("Configuration loaded - Broker: {}, S3: {}, Bucket: {}", amqp_url, s3_endpoint, bucket_name);

    info!("Connecting to RabbitMQ broker...");
    let extractor = Extractor::new(&amqp_url, &s3_endpoint, bucket_name).await
        .map_err(|e| {
            tracing::error!("Failed to initialize extractor: {}", e);
            e
        })?;

    info!("✓ Extractor initialized, starting message consumer...");
    extractor.start().await?;

    Ok(())
}
