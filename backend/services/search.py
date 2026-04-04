import json
import logging
from services.storage import get_client
from services.clip import embed_text, cosine_similarity

logger = logging.getLogger(__name__)


def _fix_url(url: str | None) -> str | None:
    """Clean malformed Supabase URLs (double slash, trailing '?')."""
    if not url:
        return url
    return url.replace("//storage/", "/storage/").rstrip("?").rstrip("&")


def search_frames(query: str, match_count: int = 5, match_threshold: float = 0.10) -> list[dict]:
    """
    Embed a text query with CLIP and search for the most similar frames.
    Tries the pgvector RPC first; falls back to Python-side similarity if the
    RPC returns nothing (e.g. missing function, type-cast issue, or no matches).
    """
    query_embedding = embed_text(query)
    client = get_client()

    # --- Attempt 1: pgvector RPC (fast path) ---
    try:
        result = client.rpc(
            "match_frames",
            {
                # Send as string so PostgreSQL uses its text→vector cast path,
                # which is more reliable than the json→vector path via PostgREST.
                "query_embedding": str(query_embedding),
                "match_threshold": match_threshold,
                "match_count": match_count,
            },
        ).execute()

        if result.data:
            logger.info("RPC search returned %d result(s)", len(result.data))
            normalized = []
            for row in result.data:
                row = dict(row)
                if "timestamp" not in row:
                    row["timestamp"] = (
                        row.get("captured_at")
                        or row.get("created_at")
                        or row.get("ts")
                        or ""
                    )
                row["image_url"] = _fix_url(row.get("image_url"))
                normalized.append(row)
            return normalized

        logger.warning(
            "RPC match_frames returned 0 results for query=%r — falling back to Python search",
            query,
        )
    except Exception as exc:
        logger.error("RPC match_frames failed (%s) — falling back to Python search", exc)

    # --- Attempt 2: Python-side similarity (reliable fallback) ---
    return _python_search(query_embedding, match_count, match_threshold)


def _python_search(
    query_embedding: list[float], match_count: int, match_threshold: float
) -> list[dict]:
    """
    Fetch all frames from Supabase and rank them by CLIP cosine similarity in Python.
    Works regardless of whether the match_frames SQL function exists.
    """
    client = get_client()
    result = client.table("frames").select("id, timestamp, image_url, embedding").execute()
    frames = result.data or []

    logger.info("Python fallback: %d frame(s) fetched from DB", len(frames))

    scored: list[dict] = []
    for frame in frames:
        raw_emb = frame.get("embedding")
        if raw_emb is None:
            logger.warning("Frame %s has NULL embedding — skipping", frame.get("id"))
            continue

        # Supabase returns vector columns as a string "[0.1, 0.2, ...]" or as a list.
        if isinstance(raw_emb, str):
            try:
                emb = json.loads(raw_emb)
            except Exception:
                logger.warning("Could not parse embedding for frame %s", frame.get("id"))
                continue
        else:
            emb = raw_emb

        sim = cosine_similarity(query_embedding, emb)
        if sim >= match_threshold:
            scored.append(
                {
                    "id": frame["id"],
                    "timestamp": frame["timestamp"],
                    "image_url": _fix_url(frame["image_url"]),
                    "similarity": round(float(sim), 4),
                }
            )

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:match_count]
