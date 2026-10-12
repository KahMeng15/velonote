"""Embeddings module for semantic search"""

import json
import logging
import os

import numpy as np

logger = logging.getLogger(__name__)

# Global embeddings model
embedding_model = None


def get_embeddings_model():
    """Get or load embeddings model"""
    global embedding_model
    if embedding_model is None:
        from sentence_transformers import SentenceTransformer

        try:
            embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            logger.info("Embeddings model loaded")
        except Exception as e:
            logger.error(f"Failed to load embeddings model: {e}")
    return embedding_model


def embed_text(text: str) -> list[float]:
    """Convert text to embedding vector"""
    model = get_embeddings_model()
    if model is None:
        return []

    try:
        embedding = model.encode(text, convert_to_tensor=False)
        return embedding.tolist()
    except Exception as e:
        logger.error(f"Error embedding text: {e}")
        return []


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Convert multiple texts to embeddings"""
    model = get_embeddings_model()
    if model is None or not texts:
        return []

    try:
        embeddings = model.encode(texts, convert_to_tensor=False)
        return embeddings.tolist()
    except Exception as e:
        logger.error(f"Error embedding texts: {e}")
        return []


def similarity(embedding1: list[float], embedding2: list[float]) -> float:
    """Calculate cosine similarity between two embeddings"""
    try:
        a = np.array(embedding1)
        b = np.array(embedding2)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    except Exception as e:
        logger.error(f"Error calculating similarity: {e}")
        return 0.0


def find_similar(
    query_embedding: list[float], embeddings: list[dict], top_k: int = 5
) -> list[dict]:
    """Find most similar embeddings"""
    if not embeddings or not query_embedding:
        return []

    similarities = []
    for i, emb_dict in enumerate(embeddings):
        sim = similarity(query_embedding, emb_dict["vector"])
        similarities.append((i, sim, emb_dict))

    # Sort by similarity descending
    similarities.sort(key=lambda x: x[1], reverse=True)

    return [s[2] for s in similarities[:top_k]]


def save_embeddings(embeddings: list[dict], path: str):
    """Save embeddings to file"""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(embeddings, f)
        logger.info(f"Saved {len(embeddings)} embeddings to {path}")
    except Exception as e:
        logger.error(f"Error saving embeddings: {e}")


def load_embeddings(path: str) -> list[dict]:
    """Load embeddings from file"""
    try:
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
        return []
    except Exception as e:
        logger.error(f"Error loading embeddings: {e}")
        return []


def find_relevant_snippets(
    query: str, text: str, top_k: int = 3, chunk_size: int = 500
) -> list[dict]:
    """
    Find the most relevant text chunks for a query using semantic similarity.

    Args:
        query: The search query
        text: The full text to search in
        top_k: Number of top snippets to return
        chunk_size: Approximate size of each chunk in characters

    Returns:
        List of dicts with 'text', 'position', and 'score' for top-k most relevant chunks
    """
    model = get_embeddings_model()
    if model is None or not text:
        return []

    try:
        # Split text into chunks and track positions
        chunks = []
        positions = []
        words = text.split()
        current_chunk = []
        current_length = 0
        char_position = 0

        for word in words:
            if not current_chunk:
                # Start position of this chunk
                positions.append(char_position)

            current_chunk.append(word)
            current_length += len(word) + 1
            char_position += len(word) + 1

            if current_length >= chunk_size:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_length = 0

        if current_chunk:
            positions.append(char_position - current_length)
            chunks.append(" ".join(current_chunk))

        if not chunks:
            return []

        # Encode query and chunks
        query_embedding = model.encode(query, convert_to_tensor=False)
        chunk_embeddings = model.encode(chunks, convert_to_tensor=False)

        # Calculate similarities
        similarities = []
        for i, chunk_emb in enumerate(chunk_embeddings):
            sim = float(
                np.dot(query_embedding, chunk_emb)
                / (np.linalg.norm(query_embedding) * np.linalg.norm(chunk_emb) + 1e-9)
            )
            similarities.append(
                {
                    "text": chunks[i],
                    "position": positions[i] if i < len(positions) else 0,
                    "score": round(sim * 100, 1),  # Convert to percentage
                    "index": i,
                }
            )

        # Sort and return top-k
        similarities.sort(key=lambda x: x["score"], reverse=True)
        return similarities[:top_k]

    except Exception as e:
        logger.error(f"Error in find_relevant_snippets: {e}")
        return []


def combine_snippets(snippets: list[dict], max_chars: int = 2000) -> str:
    """
    Combine multiple snippet dicts into a single context string with character limit.

    Args:
        snippets: List of snippet dicts with 'text' key
        max_chars: Maximum total character length

    Returns:
        Combined snippets as a single string
    """
    if not snippets:
        return ""

    combined = ""
    for snippet in snippets:
        text = snippet["text"] if isinstance(snippet, dict) else snippet
        if len(combined) + len(text) + 2 <= max_chars:
            if combined:
                combined += "\n\n"
            combined += text
        else:
            break

    return combined


def compute_and_store_embeddings(resource_id: str, text: str, db) -> int:
    """
    Compute embeddings for a resource and store them in the database.

    Args:
        resource_id: ID of the resource
        text: Full extracted text
        db: SQLAlchemy Session

    Returns:
        Number of embeddings stored
    """
    from app.models.db import ResourceEmbedding

    if not text or not text.strip():
        logger.warning(f"Resource {resource_id} has empty text, skipping embedding")
        return 0

    model = get_embeddings_model()
    if model is None:
        logger.error(f"Failed to get embeddings model for resource {resource_id}")
        return 0

    try:
        # Delete existing embeddings for this resource
        db.query(ResourceEmbedding).filter(ResourceEmbedding.resource_id == resource_id).delete()
        db.commit()

        # Clean text to remove huge base64 images or markdown images before embedding
        import re
        clean_text = re.sub(r'!\[.*?\]\(.*?\)', '', text)

        # Split text into chunks
        chunks = []
        positions = []
        words = clean_text.split()
        current_chunk = []
        current_length = 0
        char_position = 0
        chunk_size = 500  # characters

        for word in words:
            if not current_chunk:
                positions.append(char_position)

            current_chunk.append(word)
            current_length += len(word) + 1
            char_position += len(word) + 1

            if current_length >= chunk_size:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_length = 0

        if current_chunk:
            positions.append(char_position - current_length)
            chunks.append(" ".join(current_chunk))

        if not chunks:
            logger.warning(f"No chunks created for resource {resource_id}")
            return 0

        # Compute embeddings for all chunks
        embeddings = model.encode(chunks, convert_to_tensor=False)

        # Store embeddings in database
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=False)):
            pos = positions[i] if i < len(positions) else 0
            emb_record = ResourceEmbedding(
                resource_id=resource_id,
                chunk_text=chunk,
                chunk_index=i,
                embedding=embedding.tolist(),  # Convert numpy array to list
                position=pos,
            )
            db.add(emb_record)

        db.commit()
        logger.info(f"Stored {len(chunks)} embeddings for resource {resource_id}")
        return len(chunks)

    except Exception as e:
        logger.error(f"Error computing embeddings for resource {resource_id}: {e}")
        db.rollback()
        return 0


def update_resource_embeddings(resource_id: str, text: str, db) -> int:
    """
    Update embeddings when resource content changes.
    Deletes old embeddings and computes new ones.

    Args:
        resource_id: ID of the resource
        text: Updated extracted text
        db: SQLAlchemy Session

    Returns:
        Number of new embeddings stored
    """
    return compute_and_store_embeddings(resource_id, text, db)


def retrieve_relevant_chunks(query: str, resource_ids: list[str], db, top_k: int = 3) -> list[dict]:
    """
    Retrieve most relevant pre-computed chunks for a query using vector similarity.

    Args:
        query: Search query
        resource_ids: List of resource IDs to search within
        db: SQLAlchemy Session
        top_k: Number of top results to return

    Returns:
        List of dicts with 'text', 'position', 'score', 'resource_id'
    """
    from app.models.db import ResourceEmbedding

    if not resource_ids or not query:
        return []

    model = get_embeddings_model()
    if model is None:
        logger.error("Failed to get embeddings model")
        return []

    try:
        # Get all embeddings for the given resources
        embeddings_records = (
            db.query(ResourceEmbedding)
            .filter(ResourceEmbedding.resource_id.in_(resource_ids))
            .all()
        )

        if not embeddings_records:
            logger.warning(f"No embeddings found for resources {resource_ids}")
            return []

        # Compute query embedding
        query_embedding = model.encode(query, convert_to_tensor=False)

        # Calculate similarities
        similarities = []
        for record in embeddings_records:
            chunk_embedding = np.array(record.embedding)
            sim = float(
                np.dot(query_embedding, chunk_embedding)
                / (np.linalg.norm(query_embedding) * np.linalg.norm(chunk_embedding) + 1e-9)
            )
            similarities.append(
                {
                    "text": record.chunk_text,
                    "position": record.position,
                    "score": round(sim * 100, 1),
                    "resource_id": record.resource_id,
                    "chunk_index": record.chunk_index,
                }
            )

        # Sort by similarity and return top-k
        similarities.sort(key=lambda x: x["score"], reverse=True)
        return similarities[:top_k]

    except Exception as e:
        logger.error(f"Error retrieving chunks: {e}")
        return []
