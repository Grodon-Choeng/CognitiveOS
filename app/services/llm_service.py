import litellm
from litellm import acompletion, aembedding

from app.config import settings
from app.utils.logging import logger


class LLMService:
    def __init__(self) -> None:
        self.model = settings.llm_model
        self.api_key = settings.llm_api_key
        self.base_url = settings.llm_base_url

        if self.api_key:
            litellm.api_key = self.api_key
        if self.base_url:
            litellm.api_base = self.base_url

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> str:
        try:
            response = await acompletion(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            logger.debug(f"LLM chat completed: {len(content)} chars")
            return content
        except Exception as e:
            logger.error(f"LLM chat failed: {e}")
            raise

    async def chat_with_system(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        return await self.chat(messages, temperature, max_tokens)

    @staticmethod
    async def get_embedding(text: str) -> list[float]:
        try:
            response = await aembedding(
                model=settings.embedding_model,
                input=[text],
            )
            embedding = response.data[0]["embedding"]
            logger.debug(f"Generated embedding: {len(embedding)} dimensions")
            return embedding
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise

    @staticmethod
    async def get_embeddings(texts: list[str]) -> list[list[float]]:
        try:
            response = await aembedding(
                model=settings.embedding_model,
                input=texts,
            )
            embeddings = [item["embedding"] for item in response.data]
            logger.debug(f"Generated {len(embeddings)} embeddings")
            return embeddings
        except Exception as e:
            logger.error(f"Batch embedding generation failed: {e}")
            raise
