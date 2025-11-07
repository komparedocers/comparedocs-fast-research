import os
import hashlib
import uuid
import json
import asyncio
from datetime import datetime
from typing import List, Optional

import boto3
import psycopg
import aio_pika
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import PyPDF2
import io

app = FastAPI(title="Document Comparison Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Environment variables
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://minio:9000")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minio")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minio123")
S3_BUCKET = os.getenv("S3_BUCKET", "documents")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/doccompare")
BROKER_URL = os.getenv("BROKER_URL", "amqp://guest:guest@broker:5672/")

# S3 client
s3_client = boto3.client(
    's3',
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
)

# Global connection pools
db_conn = None
rabbitmq_connection = None
rabbitmq_channel = None


class DocumentResponse(BaseModel):
    doc_id: str
    filename: str
    size: int
    sha256: str
    page_count: int
    status: str
    created_at: str


class CompareRequest(BaseModel):
    left_doc_id: str
    right_doc_id: str


async def get_db():
    global db_conn
    if db_conn is None or db_conn.closed:
        db_conn = await psycopg.AsyncConnection.connect(DATABASE_URL)
    return db_conn


async def get_rabbitmq_channel():
    global rabbitmq_connection, rabbitmq_channel

    if rabbitmq_connection is None or rabbitmq_connection.is_closed:
        rabbitmq_connection = await aio_pika.connect_robust(BROKER_URL)
        rabbitmq_channel = await rabbitmq_connection.channel()

        # Declare queues
        await rabbitmq_channel.declare_queue("page.ready", durable=True)
        await rabbitmq_channel.declare_queue("ingest.pdf", durable=True)

    return rabbitmq_channel


async def ensure_bucket():
    try:
        s3_client.head_bucket(Bucket=S3_BUCKET)
    except:
        s3_client.create_bucket(Bucket=S3_BUCKET)


@app.on_event("startup")
async def startup():
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

    logger.info("="*60)
    logger.info("GATEWAY SERVICE STARTING UP")
    logger.info("="*60)
    logger.info(f"S3_ENDPOINT: {S3_ENDPOINT}")
    logger.info(f"S3_BUCKET: {S3_BUCKET}")
    logger.info(f"DATABASE_URL: {DATABASE_URL}")
    logger.info(f"BROKER_URL: {BROKER_URL}")

    logger.info("Ensuring S3 bucket exists...")
    await ensure_bucket()
    logger.info("S3 bucket ready")

    # Initialize database
    logger.info("Initializing database tables...")
    conn = await get_db()
    async with conn.cursor() as cur:
        # Create tables if they don't exist
        await cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                sha256 TEXT UNIQUE,
                filename TEXT,
                size INTEGER,
                page_count INTEGER,
                created_at TIMESTAMP,
                status TEXT
            )
        """)
        await cur.execute("""
            CREATE TABLE IF NOT EXISTS comparisons (
                id TEXT PRIMARY KEY,
                left_doc_id TEXT,
                right_doc_id TEXT,
                status TEXT,
                result JSONB,
                created_at TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)
        await conn.commit()
    logger.info("Database tables ready")
    logger.info("="*60)
    logger.info("GATEWAY SERVICE READY")
    logger.info("="*60)


def calculate_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get_pdf_page_count(data: bytes) -> int:
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(data))
        return len(pdf_reader.pages)
    except:
        return 1  # Default to 1 if can't read


async def process_pdf_pages(doc_id: str, s3_uri: str, sha256: str):
    """Background task to emit ingest message for PDF orchestrator"""
    channel = await get_rabbitmq_channel()

    message = {
        "doc_id": doc_id,
        "s3_uri": s3_uri,
        "sha256": sha256
    }

    await channel.default_exchange.publish(
        aio_pika.Message(
            body=json.dumps(message).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        ),
        routing_key="ingest.pdf",
    )


@app.post("/upload", response_model=DocumentResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """Upload a PDF document for processing"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        logger.info(f"=== UPLOAD START === Filename: {file.filename}, Content-Type: {file.content_type}")

        # Read file content
        logger.info("Reading file content...")
        content = await file.read()
        file_size = len(content)
        logger.info(f"File read successfully. Size: {file_size} bytes ({file_size / 1024 / 1024:.2f} MB)")

        # Calculate hash for deduplication
        logger.info("Calculating SHA256 hash...")
        sha256 = calculate_sha256(content)
        logger.info(f"SHA256: {sha256}")

        # Check if already exists
        logger.info("Checking for existing document in database...")
        conn = await get_db()
        async with conn.cursor() as cur:
            await cur.execute("SELECT id FROM documents WHERE sha256 = %s", (sha256,))
            existing = await cur.fetchone()

            if existing:
                logger.info(f"Document already exists with ID: {existing[0]}")
                await cur.execute("SELECT * FROM documents WHERE sha256 = %s", (sha256,))
                row = await cur.fetchone()
                return DocumentResponse(
                    doc_id=row[0],
                    filename=row[2],
                    size=row[3],
                    sha256=row[1],
                    page_count=row[4],
                    status=row[6],
                    created_at=row[5].isoformat(),
                )

        # Generate document ID
        doc_id = str(uuid.uuid4())
        logger.info(f"Generated new document ID: {doc_id}")

        # Get page count
        logger.info("Counting PDF pages...")
        page_count = get_pdf_page_count(content)
        logger.info(f"PDF has {page_count} pages")

        # Upload to S3
        logger.info(f"Uploading to S3: bucket={S3_BUCKET}")
        s3_key = f"pdfs/{sha256}.pdf"
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=content,
        )
        s3_uri = f"s3://{S3_BUCKET}/{s3_key}"
        logger.info(f"S3 upload successful: {s3_uri}")

        # Store metadata
        logger.info("Storing document metadata in database...")
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO documents (id, sha256, filename, size, page_count, created_at, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (doc_id, sha256, file.filename, len(content), page_count, datetime.utcnow(), "processing")
            )
            await conn.commit()
        logger.info("Database insert successful")

        # Emit processing event
        logger.info("Emitting ingest.pdf event to message broker...")
        background_tasks.add_task(process_pdf_pages, doc_id, s3_uri, sha256)
        logger.info("Background task scheduled")

        logger.info(f"=== UPLOAD COMPLETE === Document ID: {doc_id}")

        return DocumentResponse(
            doc_id=doc_id,
            filename=file.filename,
            size=len(content),
            sha256=sha256,
            page_count=page_count,
            status="processing",
            created_at=datetime.utcnow().isoformat(),
        )

    except Exception as e:
        logger.error(f"=== UPLOAD ERROR === {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.get("/documents")
async def list_documents():
    """List all uploaded documents"""
    conn = await get_db()
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT id, filename, size, page_count, created_at, status FROM documents ORDER BY created_at DESC"
        )
        rows = await cur.fetchall()

        return [
            {
                "doc_id": row[0],
                "filename": row[1],
                "size": row[2],
                "page_count": row[3],
                "created_at": row[4].isoformat(),
                "status": row[5],
            }
            for row in rows
        ]


@app.post("/compare")
async def compare_documents(req: CompareRequest):
    """Compare two documents"""
    import httpx
    import logging
    logger = logging.getLogger(__name__)

    logger.info("="*60)
    logger.info("=== COMPARE START ===")
    logger.info(f"Left doc: {req.left_doc_id}")
    logger.info(f"Right doc: {req.right_doc_id}")

    comparison_id = str(uuid.uuid4())
    logger.info(f"Generated comparison ID: {comparison_id}")

    # Store comparison request
    try:
        logger.info("Storing comparison request in database...")
        conn = await get_db()
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO comparisons (id, left_doc_id, right_doc_id, status, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (comparison_id, req.left_doc_id, req.right_doc_id, "processing", datetime.utcnow())
            )
            await conn.commit()
        logger.info("Comparison request stored successfully")
    except Exception as e:
        logger.error(f"Database error storing comparison: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    # Call Rust comparator service
    try:
        logger.info("Calling Rust comparator service at http://rust-comparator:8001/compare")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://rust-comparator:8001/compare",
                json={
                    "left_doc_id": req.left_doc_id,
                    "right_doc_id": req.right_doc_id,
                },
                timeout=300.0  # 5 minutes timeout
            )

            logger.info(f"Rust comparator response status: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                logger.info(f"Comparison successful. Found {len(result.get('matches', []))} matches")

                # Update comparison with result
                logger.info("Updating comparison result in database...")
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        UPDATE comparisons
                        SET status = %s, result = %s, completed_at = %s
                        WHERE id = %s
                        """,
                        ("completed", json.dumps(result), datetime.utcnow(), comparison_id)
                    )
                    await conn.commit()
                logger.info("Database updated successfully")

                logger.info("=== COMPARE COMPLETE ===")
                logger.info("="*60)
                return result
            else:
                error_text = response.text
                logger.error(f"Rust comparator failed with status {response.status_code}: {error_text}")
                raise HTTPException(status_code=500, detail=f"Comparison failed: {error_text}")

    except httpx.TimeoutException as e:
        logger.error(f"Timeout calling rust-comparator: {e}")
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE comparisons SET status = %s WHERE id = %s",
                ("failed", comparison_id)
            )
            await conn.commit()
        raise HTTPException(status_code=500, detail="Comparison timed out after 5 minutes")

    except httpx.ConnectError as e:
        logger.error(f"Cannot connect to rust-comparator service: {e}")
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE comparisons SET status = %s WHERE id = %s",
                ("failed", comparison_id)
            )
            await conn.commit()
        raise HTTPException(status_code=500, detail="Cannot connect to comparison service. Is rust-comparator running?")

    except Exception as e:
        logger.error(f"=== COMPARE ERROR === {type(e).__name__}: {str(e)}", exc_info=True)
        # Update comparison status
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE comparisons SET status = %s WHERE id = %s",
                ("failed", comparison_id)
            )
            await conn.commit()

        raise HTTPException(status_code=500, detail=f"Comparison error: {str(e)}")


@app.get("/comparisons/{comparison_id}")
async def get_comparison(comparison_id: str):
    """Get comparison result"""
    conn = await get_db()
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT * FROM comparisons WHERE id = %s",
            (comparison_id,)
        )
        row = await cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Comparison not found")

        return {
            "id": row[0],
            "left_doc_id": row[1],
            "right_doc_id": row[2],
            "status": row[3],
            "result": row[4],
            "created_at": row[5].isoformat() if row[5] else None,
            "completed_at": row[6].isoformat() if row[6] else None,
        }


@app.get("/comparisons/{comparison_id}/report")
async def get_comparison_report(comparison_id: str):
    """Generate and return HTML report for comparison"""
    from jinja2 import Template

    conn = await get_db()
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT * FROM comparisons WHERE id = %s",
            (comparison_id,)
        )
        row = await cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Comparison not found")

        result = row[4]  # result JSONB column

        if not result:
            raise HTTPException(status_code=400, detail="Comparison not yet completed")

    # Read template
    template_path = os.path.join(os.path.dirname(__file__), "report_template.html")
    if not os.path.exists(template_path):
        # Fallback to simple HTML if template not found
        template_content = """
        <html>
        <head><title>Comparison Report</title></head>
        <body>
            <h1>Comparison Report</h1>
            <h2>Summary</h2>
            <p>Compliant: {{ compliant_count }} ({{ "%.1f"|format(compliant_percentage) }}%)</p>
            <p>Non-Compliant: {{ non_compliant_count }} ({{ "%.1f"|format(non_compliant_percentage) }}%)</p>
            <h2>Details</h2>
            <table border="1" style="width:100%; border-collapse: collapse;">
                <tr>
                    <th>Left Document</th>
                    <th>Right Document</th>
                    <th>Status & Percentage</th>
                </tr>
                {% for match in matches %}
                <tr>
                    <td>{{ match.left_text[:200] }}...</td>
                    <td>{{ match.right_text[:200] }}...</td>
                    <td>
                        {% if match.match_type == 'exact' or match.match_type == 'similar' %}
                        COMPLIANT
                        {% else %}
                        NON-COMPLIANT
                        {% endif %}
                        <br>{{ "%.1f"|format(match.similarity_score * 100) }}%
                    </td>
                </tr>
                {% endfor %}
            </table>
        </body>
        </html>
        """
    else:
        with open(template_path, 'r') as f:
            template_content = f.read()

    template = Template(template_content)

    html_report = template.render(
        comparison_id=comparison_id,
        timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        **result
    )

    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html_report)


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/config")
async def get_config():
    """Get current configuration for debugging"""
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Config endpoint accessed")

    return {
        "s3_endpoint": S3_ENDPOINT,
        "s3_bucket": S3_BUCKET,
        "database_connected": db_conn is not None and not db_conn.closed if db_conn else False,
        "rabbitmq_connected": rabbitmq_connection is not None and not rabbitmq_connection.is_closed if rabbitmq_connection else False,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
