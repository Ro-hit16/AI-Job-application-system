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
                            {
                                "role": "system",
                                "content": system_prompt or "You are a helpful assistant.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                        "options": {
                            "num_predict": 1200,
                        },
                    },
                )
                response.raise_for_status()
                data = response.json()
                content = data.get("message", {}).get("content")

                if not isinstance(content, str) or not content.strip():
                    raise RuntimeError("Ollama returned an empty response")

                if content.strip().startswith("LLM error:"):
                    raise RuntimeError(content.strip())

                return content

        except Exception as e:
           raise RuntimeError(
                f"LLM generation failed: {type(e).__name__}: {str(e) or repr(e)}"
            ) from e

   
    async def generate_structured(
        self,
        prompt: str,
        system_prompt: str,
        output_schema: dict,
    ) -> dict:
        system = (
            f"{system_prompt}\n"
            "Respond ONLY with valid JSON. No markdown, no explanation, no code blocks."
        )
        text = await self.generate(prompt, system)

        text = text.strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1].strip()
            if text.startswith("json"):
                text = text[4:].strip()

        try:
            result = json.loads(text)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"LLM returned invalid JSON: {e}"
            ) from e

        if not isinstance(result, dict):
            raise RuntimeError("LLM structured response must be a JSON object")

        return result


    async def embed(self, text: str) -> list[float]:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/embeddings",
                    json={
                        "model": settings.EMBEDDING_MODEL,
                        "prompt": text,
                    },
                )
                response.raise_for_status()
                data = response.json()
                embedding = data.get("embedding")

                if not isinstance(embedding, list) or not embedding:
                    raise RuntimeError("Ollama returned an empty embedding")

                return embedding

        except Exception as e:
            raise RuntimeError(f"LLM embedding failed: {e}") from e


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