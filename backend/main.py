import os
import asyncio
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
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

# Shared frame buffer for live feed
_latest_display_frame: bytes | None = None
_frame_version = 0
_frame_condition = asyncio.Condition()


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    global _last_embedding, _latest_display_frame, _frame_version

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    # Also push to live feed
    _latest_display_frame = image_bytes
    async with _frame_condition:
        _frame_version += 1
        _frame_condition.notify_all()

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


# --- Display-only frame (no CLIP, just update live feed) ---

@app.post("/api/frames/display", status_code=204)
async def display_frame(file: UploadFile = File(...)):
    global _latest_display_frame, _frame_version
    image_bytes = await file.read()
    if not image_bytes:
        return
    _latest_display_frame = image_bytes
    async with _frame_condition:
        _frame_version += 1
        _frame_condition.notify_all()


# --- Live frame (raw JPEG, polled by frontend) ---

@app.get("/api/frames/live")
def live_frame():
    """Return the latest display frame as raw JPEG bytes."""
    if _latest_display_frame is None:
        raise HTTPException(status_code=404, detail="No frames yet")
    return Response(content=_latest_display_frame, media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


# --- Latest Frame (for live feed polling) ---

@app.get("/api/frames/latest")
def latest_frame():
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
    results = search_frames(req.query, match_count=req.match_count)
    return {"results": results}


# --- Ask (the main RAG endpoint) ---

class AskRequest(BaseModel):
    question: str


@app.post("/api/ask")
async def ask(req: AskRequest):
    # search_frames is synchronous (CLIP embed + Supabase RPC) — run in thread pool
    # so it doesn't block the event loop and freeze the live video feed
    frames = await asyncio.to_thread(search_frames, req.question, match_count=5)
    result = await ask_claude_about_frames(req.question, frames)
    return result


# --- Text-to-Speech (edge-tts, free neural voices) ---

class TTSRequest(BaseModel):
    text: str


@app.post("/api/tts")
async def tts(req: TTSRequest):
    import edge_tts
    communicate = edge_tts.Communicate(req.text, voice="en-US-AndrewNeural", rate="+5%")

    async def generate():
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]

    return StreamingResponse(
        generate(),
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )


# --- Manual reset: wipe all frames from storage + database ---

@app.delete("/api/reset")
def reset_all():
    """
    Wipe every stored frame from both Supabase Storage and the frames table.
    Resets the in-memory dedup state too.
    Call this manually from the terminal when you want a clean slate:
        curl -X DELETE http://localhost:8000/api/reset
    The code never calls this automatically.
    """
    global _last_embedding
    from services.storage import get_client, BUCKET_NAME

    client = get_client()

    # 1. Remove all files from the 'frames/' folder in storage (best-effort)
    deleted_files = 0
    try:
        files = client.storage.from_(BUCKET_NAME).list("frames")
        if files and isinstance(files, list):
            paths = [f"frames/{f['name']}" for f in files if f.get("name")]
            if paths:
                client.storage.from_(BUCKET_NAME).remove(paths)
                deleted_files = len(paths)
    except Exception as exc:
        logging.warning("Storage cleanup partial error (files may already be gone): %s", exc)

    # 2. Delete all rows from the frames table
    result = client.table("frames").delete().gte("timestamp", "1970-01-01T00:00:00+00:00").execute()
    deleted_records = len(result.data) if result.data else 0

    # 3. Reset in-memory dedup cache
    _last_embedding = None

    return {
        "status": "reset",
        "deleted_files": deleted_files,
        "deleted_records": deleted_records,
    }


# --- Debug: inspect database state ---

@app.get("/api/debug")
def debug():
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
            emb_preview = emb[:60] + "..." if isinstance(emb, str) else str(emb[:4]) + f"... ({len(emb)} dims)"
        else:
            emb_preview = None
        previews.append({"id": f["id"], "timestamp": f["timestamp"], "image_url": f["image_url"], "embedding_preview": emb_preview})
    return {"total_frames": total, "frames_with_embedding": with_embedding, "recent_frames": previews}


# --- Live Feed WebSocket ---

@app.websocket("/ws/feed")
async def feed_source(ws: WebSocket):
    """Phone connects here and sends JPEG frames as binary for live display."""
    global _latest_display_frame, _frame_version
    await ws.accept()
    try:
        while True:
            data = await ws.receive_bytes()
            _latest_display_frame = data
            async with _frame_condition:
                _frame_version += 1
                _frame_condition.notify_all()
    except WebSocketDisconnect:
        pass


@app.websocket("/ws/view")
async def feed_viewer(ws: WebSocket):
    """Frontend connects here to receive live JPEG frames. Always sends latest, drops stale."""
    await ws.accept()
    last_sent = None
    try:
        while True:
            frame = _latest_display_frame
            if frame is not None and frame is not last_sent:
                await ws.send_bytes(frame)
                last_sent = frame
            await asyncio.sleep(0.016)
    except (WebSocketDisconnect, Exception):
        pass


# --- Serve capture page ---

CAPTURE_DIR = Path(__file__).resolve().parent.parent / "capture"


@app.get("/capture")
def serve_capture():
    return FileResponse(CAPTURE_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
