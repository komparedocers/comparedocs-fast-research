use anyhow::{Context, Result};
use futures_util::StreamExt;
use lapin::{
    options::*, types::FieldTable, BasicProperties, Channel, Connection, ConnectionProperties,
};
use serde::{Deserialize, Serialize};
use std::time::Instant;
use tracing::{error, info};

#[derive(Debug, Deserialize)]
struct IngestPdfMessage {
    doc_id: String,
    s3_uri: String,
    sha256: String,
}

#[derive(Debug, Serialize)]
struct PageReadyMessage {
    doc_id: String,
    page_no: i32,
    s3_uri: String,
    sha256: String,
}

struct Orchestrator {
    _connection: Connection,
    channel: Channel,
    s3_client: aws_sdk_s3::Client,
    bucket_name: String,
}

impl Orchestrator {
    async fn new(amqp_url: &str, s3_endpoint: &str, bucket_name: String) -> Result<Self> {
        let conn = Connection::connect(amqp_url, ConnectionProperties::default())
            .await
            .context("Failed to connect to RabbitMQ")?;

        let channel = conn.create_channel().await?;

        // Declare queues
        channel
            .queue_declare(
                "ingest.pdf",
                QueueDeclareOptions {
                    durable: true,
                    ..Default::default()
                },
                FieldTable::default(),
            )
            .await?;

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

        // Configure S3 client
        let access_key = std::env::var("AWS_ACCESS_KEY_ID").unwrap_or_else(|_| "minio".to_string());
        let secret_key = std::env::var("AWS_SECRET_ACCESS_KEY").unwrap_or_else(|_| "minio123".to_string());

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

        Ok(Self {
            _connection: conn,
            channel,
            s3_client,
            bucket_name,
        })
    }

    async fn download_from_s3(&self, s3_uri: &str) -> Result<Vec<u8>> {
        let key = s3_uri
            .trim_start_matches("s3://")
            .trim_start_matches(&format!("{}/", self.bucket_name));

        let resp = self
            .s3_client
            .get_object()
            .bucket(&self.bucket_name)
            .key(key)
            .send()
            .await?;

        let data = resp.body.collect().await?;
        Ok(data.into_bytes().to_vec())
    }

    async fn process_pdf(&self, msg: IngestPdfMessage) -> Result<()> {
        let start = Instant::now();
        info!("Orchestrating PDF processing for doc {}", msg.doc_id);

        // Download PDF
        let pdf_bytes = self.download_from_s3(&msg.s3_uri).await?;

        // Load PDF to get page count
        let doc = lopdf::Document::load_mem(&pdf_bytes)?;
        let page_count = doc.get_pages().len();

        info!("PDF has {} pages, fanning out...", page_count);

        // Fan out page processing messages
        for page_no in 0..page_count {
            let page_msg = PageReadyMessage {
                doc_id: msg.doc_id.clone(),
                page_no: page_no as i32,
                s3_uri: msg.s3_uri.clone(),
                sha256: msg.sha256.clone(),
            };

            let payload = serde_json::to_vec(&page_msg)?;

            self.channel
                .basic_publish(
                    "",
                    "page.ready",
                    BasicPublishOptions::default(),
                    &payload,
                    BasicProperties::default(),
                )
                .await?;
        }

        let elapsed = start.elapsed();
        info!(
            "Fanned out {} pages for doc {} in {:?}",
            page_count, msg.doc_id, elapsed
        );

        Ok(())
    }

    async fn start(&self) -> Result<()> {
        info!("Starting PDF orchestrator worker...");

        let mut consumer = self
            .channel
            .basic_consume(
                "ingest.pdf",
                "orchestrator-worker",
                BasicConsumeOptions::default(),
                FieldTable::default(),
            )
            .await?;

        while let Some(delivery) = consumer.next().await {
            if let Ok(delivery) = delivery {
                match serde_json::from_slice::<IngestPdfMessage>(&delivery.data) {
                    Ok(msg) => {
                        if let Err(e) = self.process_pdf(msg).await {
                            error!("Error processing PDF: {}", e);
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

    let amqp_url = std::env::var("BROKER_URL")
        .unwrap_or_else(|_| "amqp://guest:guest@broker:5672".to_string());
    let s3_endpoint =
        std::env::var("S3_ENDPOINT").unwrap_or_else(|_| "http://minio:9000".to_string());
    let bucket_name = std::env::var("S3_BUCKET").unwrap_or_else(|_| "documents".to_string());

    info!("Connecting to broker at {}", amqp_url);
    let orchestrator = Orchestrator::new(&amqp_url, &s3_endpoint, bucket_name).await?;

    orchestrator.start().await?;

    Ok(())
}
