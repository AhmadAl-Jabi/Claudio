from services.storage import get_client
from services.clip import embed_text


def search_frames(query: str, match_count: int = 5, match_threshold: float = 0.15) -> list[dict]:
    """
    Embed a text query with CLIP and search for the most similar frames
    using pgvector cosine similarity in Supabase.
    """
    query_embedding = embed_text(query)

    client = get_client()
    result = client.rpc(
        "match_frames",
        {
            "query_embedding": query_embedding,
            "match_threshold": match_threshold,
            "match_count": match_count,
        },
    ).execute()

    return result.data
