import os
import base64
import httpx
import anthropic
from datetime import datetime, timezone

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

_anthropic_client: anthropic.Anthropic | None = None


def get_anthropic_client() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client


def _detect_media_type(data: bytes) -> str:
    """Detect image media type from magic bytes."""
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return "image/jpeg"


def _time_ago(timestamp_str: str) -> str:
    """Convert an ISO timestamp to a human-readable 'X minutes ago' string."""
    ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    delta = now - ts
    seconds = int(delta.total_seconds())

    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"about {minutes} minute{'s' if minutes != 1 else ''} ago"
    elif seconds < 86400:
        hours = seconds // 3600
        return f"about {hours} hour{'s' if hours != 1 else ''} ago"
    else:
        days = seconds // 86400
        return f"about {days} day{'s' if days != 1 else ''} ago"


async def ask_claude_about_frames(question: str, frames: list[dict]) -> dict:
    """
    Send the top matching frames + user question to Claude Vision.
    Returns the answer text and best matching frame.
    """
    if not frames:
        return {
            "answer": "I haven't seen that in my recent memory. Could you describe it differently?",
            "best_frame": None,
            "all_frames": [],
        }

    # Build the content array: images interleaved with timestamps
    content = []
    loaded = 0
    async with httpx.AsyncClient(timeout=10.0) as http:
        for i, frame in enumerate(frames):
            resp = await http.get(frame["image_url"])
            if resp.status_code != 200:
                # Storage URL returned an error (e.g. bucket not public); skip this frame.
                continue
            image_b64 = base64.b64encode(resp.content).decode("utf-8")
            content_type = _detect_media_type(resp.content)
            ts = frame.get("timestamp") or ""
            time_ago = _time_ago(ts) if ts else "unknown time"
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": content_type,
                    "data": image_b64,
                },
            })
            content.append({
                "type": "text",
                "text": f"[Image {i + 1}, captured {time_ago}{(' at ' + ts) if ts else ''}]",
            })
            loaded += 1

    if loaded == 0:
        return {
            "answer": (
                "I found relevant moments in memory but couldn't load the images "
                "(check that the 'frame-images' Supabase Storage bucket is set to public)."
            ),
            "best_frame": None,
            "all_frames": [],
        }

    content.append({
        "type": "text",
        "text": f"""You are Claudio, a visual memory assistant for someone with memory difficulties.
The user is asking: "{question}"

Above are the {loaded} most relevant frames from the user's recent environment, with timestamps.

Instructions:
- Examine each image carefully
- Answer the user's question based on what you see
- Be specific about locations ("on the kitchen counter", "left side of the desk")
- Include how long ago you saw it ("about 12 minutes ago")
- If no image is relevant, say "I haven't seen that recently — could you describe it differently?"
- Be warm, patient, and reassuring
- Keep your answer to 1-3 sentences
- End with: BEST_MATCH: <image number> (so we can highlight it)""",
    })

    client = get_anthropic_client()
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        messages=[{"role": "user", "content": content}],
    )

    raw_answer = response.content[0].text

    # Parse out the BEST_MATCH indicator
    best_match_idx = 0
    answer_text = raw_answer
    if "BEST_MATCH:" in raw_answer:
        parts = raw_answer.rsplit("BEST_MATCH:", 1)
        answer_text = parts[0].strip()
        try:
            best_match_idx = int(parts[1].strip()) - 1  # 1-indexed to 0-indexed
        except ValueError:
            best_match_idx = 0

    best_match_idx = max(0, min(best_match_idx, len(frames) - 1))

    return {
        "answer": answer_text,
        "best_frame": {
            "image_url": frames[best_match_idx].get("image_url"),
            "timestamp": frames[best_match_idx].get("timestamp", ""),
        },
        "all_frames": [
            {
                "image_url": f.get("image_url"),
                "timestamp": f.get("timestamp", ""),
                "similarity": f.get("similarity", 0),
            }
            for f in frames
        ],
    }
