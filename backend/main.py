import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from services.clip import embed_image, cosine_similarity
from services.storage import upload_frame, store_frame_record, get_latest_frame
from services.search import search_frames
from services.vision import ask_claude_about_frames

import logging
logging.basicConfig(level=logging.INFO)

# Track the last stored embedding for deduplication
_last_embedding: list[float] | None = None
DEDUP_THRESHOLD = 0.95


@asynccontextmanager
async def lifespan(app: FastAPI):
    # CLIP model loads at import time (services/clip.py module level).
    # This lifespan just confirms startup is complete.
    print("Claudio backend ready — CLIP model loaded.")
    yield


app = FastAPI(title="Claudio", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Health Check ---

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "claudio"}


# --- Frame Ingestion ---

@app.post("/api/frames", status_code=201)
async def ingest_frame(file: UploadFile = File(...)):
    """
    Receive a JPEG frame from the capture app.
    Embed with CLIP, deduplicate, store in Supabase.
    """
    global _last_embedding

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    # Embed the frame with CLIP
    embedding = embed_image(image_bytes)

    # Deduplication: skip if scene hasn't changed
    if _last_embedding is not None:
        sim = cosine_similarity(embedding, _last_embedding)
        if sim > DEDUP_THRESHOLD:
            return {"status": "skipped", "reason": "duplicate", "similarity": sim}

    # Upload image to Supabase Storage
    image_url, timestamp = upload_frame(image_bytes)

    # Store frame record with embedding in pgvector
    record = store_frame_record(image_url, embedding, timestamp)

    _last_embedding = embedding

    return {"status": "stored", "frame_id": record["id"], "image_url": image_url}


# --- Latest Frame (for live feed polling) ---

@app.get("/api/frames/latest")
def latest_frame():
    """Return the most recent frame for the live feed display."""
    frame = get_latest_frame()
    if not frame:
        raise HTTPException(status_code=404, detail="No frames captured yet")
    return frame


# --- Search ---

class SearchRequest(BaseModel):
    query: str
    match_count: int = 5


@app.post("/api/search")
def search(req: SearchRequest):
    """Semantic search over stored frames using CLIP text embedding."""
    results = search_frames(req.query, match_count=req.match_count)
    return {"results": results}


# --- Ask (the main RAG endpoint) ---

class AskRequest(BaseModel):
    question: str


@app.post("/api/ask")
async def ask(req: AskRequest):
    """
    The core Claudio interaction:
    1. CLIP-embed the question text
    2. pgvector search for top matching frames
    3. Send frames + question to Claude Vision
    4. Return natural language answer + best frame
    """
    # Search for relevant frames
    frames = search_frames(req.question, match_count=5)

    # Ask Claude to analyze the frames and answer
    result = await ask_claude_about_frames(req.question, frames)

    return result


# --- Debug: inspect database state ---

@app.get("/api/debug")
def debug():
    """
    Returns diagnostic info about what is stored in Supabase:
    - total frame count
    - how many frames have a non-NULL embedding
    - the 3 most recent frames (id, timestamp, image_url, embedding preview)
    Useful for verifying that the capture pipeline is working end-to-end.
    """
    from services.storage import get_client
    client = get_client()

    result = client.table("frames").select("id, timestamp, image_url, embedding").order("timestamp", desc=True).execute()
    frames = result.data or []

    total = len(frames)
    with_embedding = sum(1 for f in frames if f.get("embedding") is not None)

    previews = []
    for f in frames[:3]:
        emb = f.get("embedding")
        if emb is not None:
            if isinstance(emb, str):
                emb_preview = emb[:60] + "..."
            else:
                emb_preview = str(emb[:4]) + f"... ({len(emb)} dims)"
        else:
            emb_preview = None
        previews.append({
            "id": f["id"],
            "timestamp": f["timestamp"],
            "image_url": f["image_url"],
            "embedding_preview": emb_preview,
        })

    return {
        "total_frames": total,
        "frames_with_embedding": with_embedding,
        "recent_frames": previews,
    }


# --- Serve capture page ---

CAPTURE_DIR = Path(__file__).resolve().parent.parent / "capture"


@app.get("/capture")
def serve_capture():
    return FileResponse(CAPTURE_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
