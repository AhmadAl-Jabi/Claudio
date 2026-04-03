from sentence_transformers import SentenceTransformer
from PIL import Image
import io
import numpy as np

# Load once at import time — ~350MB, takes 10-30s first time
model = SentenceTransformer("clip-ViT-B-32")


def embed_image(image_bytes: bytes) -> list[float]:
    """Embed a raw JPEG into a 512-dim vector."""
    image = Image.open(io.BytesIO(image_bytes))
    embedding = model.encode(image)
    return embedding.tolist()


def embed_text(text: str) -> list[float]:
    """Embed a text query into the same 512-dim vector space."""
    embedding = model.encode(text)
    return embedding.tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    a_np, b_np = np.array(a), np.array(b)
    return float(np.dot(a_np, b_np) / (np.linalg.norm(a_np) * np.linalg.norm(b_np)))
