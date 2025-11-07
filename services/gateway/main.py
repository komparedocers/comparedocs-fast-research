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
    await ensure_bucket()

    # Initialize database
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

    # Read file content
    content = await file.read()

    # Calculate hash for deduplication
    sha256 = calculate_sha256(content)

    # Check if already exists
    conn = await get_db()
    async with conn.cursor() as cur:
        await cur.execute("SELECT id FROM documents WHERE sha256 = %s", (sha256,))
        existing = await cur.fetchone()

        if existing:
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

    # Get page count
    page_count = get_pdf_page_count(content)

    # Upload to S3
    s3_key = f"pdfs/{sha256}.pdf"
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=s3_key,
        Body=content,
    )
    s3_uri = f"s3://{S3_BUCKET}/{s3_key}"

    # Store metadata
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO documents (id, sha256, filename, size, page_count, created_at, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (doc_id, sha256, file.filename, len(content), page_count, datetime.utcnow(), "processing")
        )
        await conn.commit()

    # Emit processing event
    background_tasks.add_task(process_pdf_pages, doc_id, s3_uri, sha256)

    return DocumentResponse(
        doc_id=doc_id,
        filename=file.filename,
        size=len(content),
        sha256=sha256,
        page_count=page_count,
        status="processing",
        created_at=datetime.utcnow().isoformat(),
    )


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

    comparison_id = str(uuid.uuid4())

    # Store comparison request
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

    # Call Rust comparator service
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://rust-comparator:8001/compare",
                json={
                    "left_doc_id": req.left_doc_id,
                    "right_doc_id": req.right_doc_id,
                },
                timeout=300.0  # 5 minutes timeout
            )

            if response.status_code == 200:
                result = response.json()

                # Update comparison with result
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

                return result
            else:
                raise HTTPException(status_code=500, detail="Comparison failed")

    except Exception as e:
        # Update comparison status
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE comparisons SET status = %s WHERE id = %s",
                ("failed", comparison_id)
            )
            await conn.commit()

        raise HTTPException(status_code=500, detail=str(e))


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
