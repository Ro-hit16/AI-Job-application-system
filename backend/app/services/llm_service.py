import asyncio
import json
import os

import httpx

from app.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)

JOB_SKILL_EXTRACTION_SYSTEM_PROMPT = """
Extract required skills, experience, and job details from a job description.
"""

RESUME_SKILL_EXTRACTION_SYSTEM_PROMPT = """
Extract skills, education, experience, and contact information from a resume.
"""

COVER_LETTER_SYSTEM_PROMPT = """
You write concise, factual cover letters in plain text. Use only facts present in
the candidate background. Never invent employers, skills, tools or numbers.
Never use placeholders such as [Your Name]. Separate paragraphs with one blank line.
"""

RESUME_TAILOR_SYSTEM_PROMPT = """
You are a careful resume editor. You only reword existing bullet points to fit a
job. You never add technologies, tools, skills, employers or numbers that are not
already in the candidate's background. You reply with a single JSON object and
nothing else.
"""


class LLMError(RuntimeError):
    """Any LLM failure. Subclasses RuntimeError so existing handlers still work."""


_TRANSIENT = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    asyncio.TimeoutError,
)

# CPU inference: one generation at a time, otherwise requests queue inside Ollama
# and every one of them times out.
_OLLAMA_LOCK = asyncio.Semaphore(1)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _timeout(read: float | None = None) -> httpx.Timeout:
    # With streaming, `read` is the max wait for the NEXT chunk (first token
    # includes prompt evaluation on CPU), not the whole generation.
    return httpx.Timeout(
        connect=_env_float("OLLAMA_CONNECT_TIMEOUT", 10.0),
        read=read or _env_float("OLLAMA_READ_TIMEOUT", 180.0),
        write=30.0,
        pool=10.0,
    )


class LLMService:
    def __init__(self) -> None:
        self._transport: httpx.AsyncBaseTransport | None = None  # test hook
        self._retry_backoff = 2.0

    async def _stream_chat(self, payload: dict) -> str:
        parts: list[str] = []
        done_reason = None
        async with httpx.AsyncClient(timeout=_timeout(), transport=self._transport) as client:
            async with client.stream(
                "POST", f"{settings.OLLAMA_BASE_URL}/api/chat", json=payload
            ) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode(errors="replace")[:300]
                    raise LLMError(f"Ollama HTTP {resp.status_code}: {body}")
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if "error" in chunk:
                        raise LLMError(f"Ollama error: {chunk['error']}")
                    parts.append(chunk.get("message", {}).get("content", ""))
                    if chunk.get("done"):
                        done_reason = chunk.get("done_reason")
        text = "".join(parts)
        if not text.strip():
            raise LLMError("Ollama returned an empty response")
        if done_reason == "length":
            raise LLMError(
                f"Ollama output truncated at num_predict={payload['options']['num_predict']}"
            )
        return text

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        *,
        max_tokens: int | None = None,
        json_mode: bool = False,
        temperature: float = 0.2,
    ) -> str:
        payload = {
            "model": settings.LLM_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt or "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
            "stream": True,
            "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "30m"),
            "options": {
                "num_ctx": _env_int("OLLAMA_NUM_CTX", 4096),
                "num_predict": max_tokens or _env_int("OLLAMA_NUM_PREDICT", 800),
                "temperature": temperature,
            },
        }
        if json_mode:
            payload["format"] = "json"

        attempts = _env_int("OLLAMA_MAX_ATTEMPTS", 2)
        total = _env_float("OLLAMA_TOTAL_TIMEOUT", 420.0)
        last: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                async with _OLLAMA_LOCK:
                    return await asyncio.wait_for(self._stream_chat(payload), timeout=total)
            except _TRANSIENT as e:  # retry only transient failures
                last = e
                logger.warning(
                    "Ollama transient failure",
                    extra={"attempt": attempt, "error": f"{type(e).__name__}: {e or repr(e)}"},
                )
                if attempt < attempts:
                    await asyncio.sleep(self._retry_backoff * attempt)
            except LLMError:
                raise
            except Exception as e:
                raise LLMError(
                    f"LLM generation failed: {type(e).__name__}: {str(e) or repr(e)}"
                ) from e
        raise LLMError(
            f"LLM generation failed after {attempts} attempts: "
            f"{type(last).__name__}: {str(last) or repr(last)}"
        ) from last

    async def generate_structured(
        self,
        prompt: str,
        system_prompt: str,
        output_schema: dict,
        max_tokens: int | None = None,
    ) -> dict:
        system = (
            f"{system_prompt}\n"
            "Respond ONLY with valid JSON. No markdown, no explanation, no code blocks."
        )
        text = (await self.generate(prompt, system, max_tokens=max_tokens, json_mode=True)).strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1].strip()
            if text.startswith("json"):
                text = text[4:].strip()
        try:
            result = json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"LLM returned invalid JSON: {e}") from e
        if not isinstance(result, dict):
            raise LLMError("LLM structured response must be a JSON object")
        return result

    async def embed(self, text: str) -> list[float]:
        # NOTE: the old second `embed` (returned [0.1]*384 on any error) was removed.
        try:
            async with httpx.AsyncClient(timeout=_timeout(read=60.0)) as client:
                response = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/embeddings",
                    json={"model": settings.EMBEDDING_MODEL, "prompt": text},
                )
                response.raise_for_status()
                embedding = response.json().get("embedding")
                if not isinstance(embedding, list) or not embedding:
                    raise RuntimeError("Ollama returned an empty embedding")
                return embedding
        except Exception as e:
            raise LLMError(f"LLM embedding failed: {type(e).__name__}: {e or repr(e)}") from e

        async def chat(self, messages: list[dict], system_prompt: str = "") -> str:
            """Multi-turn chat. Raises LLMError on any failure (never returns error text)."""
            chat_messages = []
            if system_prompt:
                chat_messages.append({"role": "system", "content": system_prompt})
            chat_messages.extend(messages)
            try:
                async with httpx.AsyncClient(
                    timeout=_timeout(read=120.0), transport=self._transport
                ) as client:
                    response = await client.post(
                        f"{settings.OLLAMA_BASE_URL}/api/chat",
                        json={
                            "model": settings.LLM_MODEL,
                            "messages": chat_messages,
                            "stream": False,
                            "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "30m"),
                        },
                    )
                    response.raise_for_status()
                    data = response.json()
            except Exception as e:
                raise LLMError(f"LLM chat failed: {type(e).__name__}: {str(e) or repr(e)}") from e
            if isinstance(data, dict) and "error" in data:
                raise LLMError(f"Ollama error: {data['error']}")
            content = (data.get("message") or {}).get("content") if isinstance(data, dict) else None
            if not isinstance(content, str) or not content.strip():
                raise LLMError("LLM chat returned an empty response")
            return content


_llm_service = LLMService()


def get_llm_service():
    return _llm_service