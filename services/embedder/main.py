import os
import json
import asyncio
import aio_pika
from sentence_transformers import SentenceTransformer

# Configuration
BROKER_URL = os.getenv("BROKER_URL", "amqp://guest:guest@broker:5672/")
MODEL_NAME = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# Load model
print(f"Loading model: {MODEL_NAME}")
model = SentenceTransformer(MODEL_NAME)


async def process_chunks(message: aio_pika.IncomingMessage):
    async with message.process():
        data = json.loads(message.body.decode())

        doc_id = data.get("doc_id")
        page_no = data.get("page_no")
        chunks = data.get("chunks", [])

        print(f"Processing embeddings for doc {doc_id}, page {page_no}, {len(chunks)} chunks")

        # Generate embeddings
        texts = [chunk["text"] for chunk in chunks]
        if texts:
            embeddings = model.encode(texts, show_progress_bar=False)

            # In production, store these in pgvector or similar
            print(f"Generated {len(embeddings)} embeddings")


async def main():
    connection = await aio_pika.connect_robust(BROKER_URL)
    channel = await connection.channel()

    # Declare queue
    queue = await channel.declare_queue("page.chunked", durable=True)

    print("Embedder service started, waiting for messages...")

    await queue.consume(process_chunks)

    # Keep running
    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
