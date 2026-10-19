"""Provider adapter. Uses structured Responses output, not regex-extracted JSON."""
import json
from dataclasses import dataclass
from typing import Any, Protocol


from app.config import get_settings


@dataclass(frozen=True)
class MeterEntry:
    model: str
    input_tokens: int
    output_tokens: int


class ModelProvider(Protocol):
    meter: list[MeterEntry]

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def structured(self, name: str, system: str, user: str, schema: dict) -> dict: ...


class OpenAIProvider:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for AI processing")
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=2,
        )
        self.model = settings.openai_model
        self.embedding_model = settings.embedding_model
        self.meter: list[MeterEntry] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        result = await self.client.embeddings.create(model=self.embedding_model, input=texts)
        self.meter.append(MeterEntry(
            self.embedding_model,
            int(result.usage.prompt_tokens) if result.usage else 0,
            0,
        ))
        vectors = [record.embedding for record in sorted(result.data, key=lambda row: row.index)]
        if any(len(vec) != 1536 for vec in vectors):
            raise RuntimeError("Embedding dimensions changed: expected 1536")
        return vectors

    async def structured(self, name: str, system: str, user: str, schema: dict) -> dict:
        response = await self.client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            text={"format": {"type": "json_schema", "name": name, "strict": True, "schema": schema}},
            max_output_tokens=1600,
            store=False,
        )
        usage = response.usage
        self.meter.append(MeterEntry(
            self.model, int(usage.input_tokens) if usage else 0,
            int(usage.output_tokens) if usage else 0,
        ))
        if response.status != "completed" or not response.output_text:
            raise RuntimeError("LLM returned incomplete or refused structured output")
        return json.loads(response.output_text)
