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


def upload_frame(image_bytes: bytes) -> tuple[str, str]:
    """Upload a frame to Supabase Storage. Returns (public_url, iso_timestamp)."""
    client = get_client()
    now = datetime.now(timezone.utc)
    timestamp_tag = now.strftime("%Y%m%dT%H%M%S_%f")
    file_name = f"frame_{timestamp_tag}.jpg"
    file_path = f"frames/{file_name}"

    response = client.storage.from_(BUCKET_NAME).upload(
        path=file_path,
        file=image_bytes,
        file_options={"content-type": "image/jpeg"},
    )
    # supabase-py returns an error dict on failure instead of raising
    if isinstance(response, dict) and response.get("error"):
        raise RuntimeError(f"Storage upload failed: {response['error']}")

    public_url = client.storage.from_(BUCKET_NAME).get_public_url(file_path)
    # Some supabase-py versions emit a double slash and/or trailing '?' — clean both.
    public_url = public_url.replace("//storage/", "/storage/").rstrip("?").rstrip("&")
    return public_url, now.isoformat()


def store_frame_record(image_url: str, embedding: list[float], timestamp: str) -> dict:
    """Insert a frame record into the frames table with its CLIP embedding."""
    client = get_client()
    result = (
        client.table("frames")
        .insert({
            "image_url": image_url,
            "embedding": embedding,
            "timestamp": timestamp,
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
