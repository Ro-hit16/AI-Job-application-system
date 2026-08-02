"""
services/vector_service.py — ChromaDB Vector Store Operations
"""

import uuid
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import get_settings
from app.core.exceptions import VectorDBException
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class VectorService:
    def __init__(self):
        try:
            self._client = chromadb.HttpClient(
                host=settings.CHROMA_HOST,
                port=settings.CHROMA_PORT,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._jobs_collection = self._client.get_or_create_collection(
                name=settings.CHROMA_COLLECTION_JOBS,
                metadata={"hnsw:space": "cosine"},
            )
            self._resumes_collection = self._client.get_or_create_collection(
                name=settings.CHROMA_COLLECTION_RESUMES,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("VectorService initialized", extra={"host": settings.CHROMA_HOST})
        except Exception as e:
            raise VectorDBException("init", str(e))

    async def add_job_embedding(self, job_id: str, vector: list[float], metadata: dict) -> str:
        try:
            embedding_id = str(uuid.uuid4())
            self._jobs_collection.add(
                ids=[embedding_id],
                embeddings=[vector],
                metadatas=[{**metadata, "job_id": job_id}],
            )
            return embedding_id
        except Exception as e:
            raise VectorDBException("add_job_embedding", str(e))

    async def add_resume_embedding(self, resume_id: str, vector: list[float], metadata: dict) -> str:
        try:
            embedding_id = str(uuid.uuid4())
            self._resumes_collection.add(
                ids=[embedding_id],
                embeddings=[vector],
                metadatas=[{**metadata, "resume_id": resume_id}],
            )
            return embedding_id
        except Exception as e:
            raise VectorDBException("add_resume_embedding", str(e))

    async def query_similar_jobs(self, resume_vector: list[float], n_results: int = 20) -> list[dict]:
        try:
            results = self._jobs_collection.query(
                query_embeddings=[resume_vector],
                n_results=n_results,
                include=["metadatas", "distances"],
            )
            jobs = []
            for i, metadata in enumerate(results["metadatas"][0]):
                distance = results["distances"][0][i]
                score = round((1 - distance) * 100, 2)
                jobs.append({**metadata, "match_score": score})
            return sorted(jobs, key=lambda x: x["match_score"], reverse=True)
        except Exception as e:
            raise VectorDBException("query_similar_jobs", str(e))

    async def compute_similarity_score(self, job_vector: list[float], resume_vector: list[float]) -> float:
        try:
            dot_product = sum(a * b for a, b in zip(job_vector, resume_vector))
            norm_a = sum(a ** 2 for a in job_vector) ** 0.5
            norm_b = sum(b ** 2 for b in resume_vector) ** 0.5
            if norm_a == 0 or norm_b == 0:
                return 0.0
            cosine_sim = dot_product / (norm_a * norm_b)
            return round(((cosine_sim + 1) / 2) * 100, 2)
        except Exception as e:
            raise VectorDBException("compute_similarity", str(e))

    async def delete_job_embedding(self, embedding_id: str) -> None:
        try:
            self._jobs_collection.delete(ids=[embedding_id])
        except Exception as e:
            raise VectorDBException("delete_job_embedding", str(e))

    async def health_check(self) -> dict:
        try:
            self._client.heartbeat()
            return {
                "status": "healthy",
                "jobs_count": self._jobs_collection.count(),
                "resumes_count": self._resumes_collection.count(),
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


_instance: Optional[VectorService] = None


def get_vector_service() -> VectorService:
    global _instance
    if _instance is None:
        try:
            _instance = VectorService()
        except Exception as e:
            logger.warning(f"ChromaDB unavailable, using stub: {e}")
            _instance = StubVectorService()
    return _instance


class StubVectorService:
    async def add_job_embedding(self, job_id, vector, metadata): return str(uuid.uuid4())
    async def add_resume_embedding(self, resume_id, vector, metadata): return str(uuid.uuid4())
    async def query_similar_jobs(self, resume_vector, n_results=20): return []
    async def compute_similarity_score(self, job_vector, resume_vector): return 80.0
    async def delete_job_embedding(self, embedding_id): pass
    async def health_check(self): return {"status": "stub"}