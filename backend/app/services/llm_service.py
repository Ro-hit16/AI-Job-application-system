import json
import httpx

from app.config import get_settings

settings = get_settings()

JOB_SKILL_EXTRACTION_SYSTEM_PROMPT = """
Extract required skills, experience, and job details from a job description.
"""

RESUME_SKILL_EXTRACTION_SYSTEM_PROMPT = """
Extract skills, education, experience, and contact information from a resume.
"""

COVER_LETTER_SYSTEM_PROMPT = """
Generate a professional cover letter tailored to the job description.
"""

RESUME_TAILOR_SYSTEM_PROMPT = """
Tailor a resume to match the target job description while preserving factual accuracy.
"""


class LLMService:
    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": settings.LLM_MODEL,
                        "messages": [
                            {"role": "system", "content": system_prompt or "You are a helpful assistant."},
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                    },
                )
                data = response.json()
                return data["message"]["content"]
        except Exception as e:
            return f"LLM error: {e}"

    async def generate_structured(
        self,
        prompt: str,
        system_prompt: str,
        output_schema: dict,
    ) -> dict:
        system = f"{system_prompt}\nRespond ONLY with valid JSON. No markdown, no explanation, no code blocks."
        text = await self.generate(prompt, system)
        try:
            # Strip markdown code blocks if present
            text = text.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text.strip())
        except Exception:
            return output_schema

    async def chat(self, messages: list[dict], system_prompt: str = "") -> str:
        """Multi-turn conversational chat for interview use."""
        try:
            chat_messages = []
            if system_prompt:
                chat_messages.append({"role": "system", "content": system_prompt})
            chat_messages.extend(messages)

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": settings.LLM_MODEL,
                        "messages": chat_messages,
                        "stream": False,
                    },
                )
                data = response.json()
                return data["message"]["content"]
        except Exception as e:
            return f"LLM error: {e}"

    async def embed(self, text: str) -> list[float]:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/embeddings",
                    json={"model": settings.EMBEDDING_MODEL, "prompt": text},
                )
                data = response.json()
                return data["embedding"]
        except Exception:
            return [0.1] * 384


_llm_service = LLMService()


def get_llm_service():
    return _llm_service