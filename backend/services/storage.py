import os
from datetime import datetime, timezone
from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

BUCKET_NAME = "frame-images"

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def upload_frame(image_bytes: bytes) -> str:
    """Upload a JPEG frame to Supabase Storage. Returns the public URL."""
    client = get_client()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%f")
    file_name = f"frame_{timestamp}.jpg"
    file_path = f"frames/{file_name}"

    client.storage.from_(BUCKET_NAME).upload(
        path=file_path,
        file=image_bytes,
        file_options={"content-type": "image/jpeg"},
    )

    public_url = client.storage.from_(BUCKET_NAME).get_public_url(file_path)
    return public_url


def store_frame_record(image_url: str, embedding: list[float]) -> dict:
    """Insert a frame record into the frames table with its CLIP embedding."""
    client = get_client()
    result = (
        client.table("frames")
        .insert({
            "image_url": image_url,
            "embedding": embedding,
        })
        .execute()
    )
    return result.data[0]


def get_latest_frame() -> dict | None:
    """Get the most recently stored frame."""
    client = get_client()
    result = (
        client.table("frames")
        .select("id, image_url, timestamp")
        .order("timestamp", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None
