"""Semantic search and embeddings module"""

import numpy as np


class EmbeddingsManager:
    """Manage text embeddings and semantic search"""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """Initialize embeddings model"""
        from sentence_transformers import SentenceTransformer

        try:
            logger.info(f"Loading embeddings model: {model_name}")
            self.model = SentenceTransformer(model_name)
            self.embedding_dim = self.model.get_sentence_embedding_dimension()
            logger.info(f"Model loaded. Embedding dimension: {self.embedding_dim}")
        except Exception as e:
            logger.error(f"Error loading embeddings model: {e}")
            raise

    def embed_text(self, text: str) -> np.ndarray:
        """Convert text to embeddings"""
        try:
            embedding = self.model.encode(text, convert_to_numpy=True)
            return embedding
        except Exception as e:
            logger.error(f"Error embedding text: {e}")
            raise

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """Convert multiple texts to embeddings"""
        try:
            embeddings = self.model.encode(texts, convert_to_numpy=True)
            return embeddings
        except Exception as e:
            logger.error(f"Error embedding texts: {e}")
            raise

    def cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors"""
        try:
            dot_product = np.dot(vec1, vec2)
            norm_vec1 = np.linalg.norm(vec1)
            norm_vec2 = np.linalg.norm(vec2)

            if norm_vec1 == 0 or norm_vec2 == 0:
                return 0.0

            similarity = dot_product / (norm_vec1 * norm_vec2)
            return float(similarity)
        except Exception as e:
            logger.error(f"Error calculating similarity: {e}")
            raise

    def search(self, query: str, documents: List[str], top_k: int = 5) -> List[Tuple[str, float]]:
        """
        Search for most similar documents to query

        Args:
            query: Search query
            documents: List of documents to search
            top_k: Number of top results to return

        Returns:
            List of (document, similarity_score) tuples
        """
        try:
            query_embedding = self.embed_text(query)
            doc_embeddings = self.embed_texts(documents)

            similarities = []
            for doc, embedding in zip(documents, doc_embeddings, strict=False):
                similarity = self.cosine_similarity(query_embedding, embedding)
                similarities.append((doc, similarity))

            # Sort by similarity score (descending)
            similarities.sort(key=lambda x: x[1], reverse=True)

            return similarities[:top_k]
        except Exception as e:
            logger.error(f"Error searching documents: {e}")
            raise

    def batch_search(
        self, query: str, documents: List[str], chunk_size: int = 1000, top_k: int = 5
    ) -> List[Tuple[str, float]]:
        """
        Search through large document collections in batches
        Useful for large corpuses
        """
        try:
            all_results = []

            for i in range(0, len(documents), chunk_size):
                batch = documents[i : i + chunk_size]
                results = self.search(query, batch, top_k=len(batch))
                all_results.extend(results)

            # Sort globally and return top_k
            all_results.sort(key=lambda x: x[1], reverse=True)
            return all_results[:top_k]
        except Exception as e:
            logger.error(f"Error in batch search: {e}")
            raise
