import os
import logging
import base64
import httpx
import anthropic
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

_anthropic_client: anthropic.AsyncAnthropic | None = None


def get_anthropic_client() -> anthropic.AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
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


def _format_clip_time(timestamp_str: str) -> str:
    """
    Return a label like "3:24 PM (about 5 minutes ago)" for a clip timestamp.
    Uses the server's local timezone for the clock time.
    """
    ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    delta = now - ts
    seconds = int(delta.total_seconds())

    # Relative part
    if seconds < 60:
        relative = "just now"
    elif seconds < 3600:
        minutes = seconds // 60
        relative = f"about {minutes} minute{'s' if minutes != 1 else ''} ago"
    elif seconds < 86400:
        hours = seconds // 3600
        relative = f"about {hours} hour{'s' if hours != 1 else ''} ago"
    else:
        days = seconds // 86400
        relative = f"about {days} day{'s' if days != 1 else ''} ago"

    # Exact local clock time (strip leading zero for Windows/Unix compat)
    local_ts = ts.astimezone()
    clock = local_ts.strftime("%I:%M %p").lstrip("0") or local_ts.strftime("%I:%M %p")

    return f"{clock} ({relative})"


async def _classify_intent(question: str) -> str:
    """Returns 'VISUAL' if the question is about locating or timing something, 'CHAT' otherwise."""
    client = get_anthropic_client()
    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=5,
        messages=[{
            "role": "user",
            "content": f'The user said: "{question}"\n\nDid the user ask where something is, when something was last seen or placed, or need help locating an item? If yes, reply with "VISUAL". If no, reply with "CHAT".'
        }],
    )
    result = response.content[0].text.strip().upper()
    return "VISUAL" if result.startswith("VISUAL") else "CHAT"


async def ask_claude_about_frames(question: str, frames: list[dict]) -> dict:
    """
    Send the top matching frames + user question to Claude Vision.
    Returns the answer text and best matching frame.
    """
    intent = await _classify_intent(question)

    if intent == "CHAT":
        client = get_anthropic_client()
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=150,
            messages=[{
                "role": "user",
                "content": f'You are Claudio, a friendly memory assistant for a user with dementia. The user said: "{question}"\n\nRespond naturally and briefly. Only use plain ASCII characters.'
            }],
        )
        return {
            "answer": response.content[0].text.strip(),
            "best_frame": None,
            "all_frames": [],
        }

    if not frames:
        return {
            "answer": "I haven't seen that recently.",
            "best_frame": None,
            "all_frames": [],
        }

    # Build the content array: clips interleaved with time context
    content = []
    loaded = 0
    loaded_frames = []  # frames that actually loaded, in order
    async with httpx.AsyncClient(timeout=10.0) as http:
        for frame in frames:
            resp = await http.get(frame["image_url"])
            if resp.status_code != 200:
                logger.warning(
                    "Frame image not accessible (HTTP %s), skipping: %s",
                    resp.status_code, frame.get("image_url", "?"),
                )
                continue
            image_b64 = base64.b64encode(resp.content).decode("utf-8")
            content_type = _detect_media_type(resp.content)
            ts = frame.get("timestamp") or ""
            clip_time = _format_clip_time(ts) if ts else "unknown time"
            content.append({
                "type": "text",
                "text": f"[#{loaded + 1} | {clip_time}]",
            })
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": content_type,
                    "data": image_b64,
                },
            })
            loaded_frames.append(frame)
            loaded += 1

    if loaded == 0:
        return {
            "answer": "I haven't seen that recently.",
            "best_frame": None,
            "all_frames": [],
        }

    content.append({
        "type": "text",
        "text": f"""You are Claudio, an always-on memory assistant worn as glasses. You have been passively watching the user's environment.

The user is asking: "{question}"

Each observation above is labelled [#N | <time>]. Use these labels ONLY to select your BEST_MATCH number — never mention them in your spoken response.

Rules for your response text:
- Speak in first person as a continuous memory: "I saw...", "I noticed...", "It was...". NEVER say "clip", "image", "photo", "picture", "frame", "scene", "record", or any similar word.
- NEVER describe or reference multiple observations. Pick the single best one and describe only that.
- If you can identify what the user is asking about: state (1) the exact clock time from its label (e.g. "at 3:24 PM") and (2) precisely where it was. Max 2 sentences. Omitting the time is not allowed.
- If none of the observations show what they are asking about: say you have not seen it recently. Do NOT mention any time. Max 1 sentence.
- Only use plain ASCII characters (no special dashes or symbols).

End your response with exactly one of:
  BEST_MATCH: <N>
  BEST_MATCH: NONE""",
    })

    client = get_anthropic_client()
    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=200,
        messages=[{"role": "user", "content": content}],
    )

    raw_answer = response.content[0].text

    # Parse the BEST_MATCH token
    best_match_idx = None
    answer_text = raw_answer
    if "BEST_MATCH:" in raw_answer:
        parts = raw_answer.rsplit("BEST_MATCH:", 1)
        answer_text = parts[0].strip()
        token = parts[1].strip().upper()
        if token != "NONE":
            try:
                idx = int(token) - 1  # 1-indexed to 0-indexed
                best_match_idx = max(0, min(idx, len(loaded_frames) - 1))
            except ValueError:
                best_match_idx = None

    best_frame = None
    if best_match_idx is not None:
        best_frame = {
            "image_url": loaded_frames[best_match_idx].get("image_url"),
            "timestamp": loaded_frames[best_match_idx].get("timestamp", ""),
        }

    return {
        "answer": answer_text,
        "best_frame": best_frame,
        "all_frames": [
            {
                "image_url": f.get("image_url"),
                "timestamp": f.get("timestamp", ""),
                "similarity": f.get("similarity", 0),
            }
            for f in frames
        ],
    }
