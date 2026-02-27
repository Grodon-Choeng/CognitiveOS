import hashlib

import litellm
from cashews import cache
from litellm import acompletion, aembedding

from app.config import settings
from app.constants import CACHE_DEFAULT_TTL
from app.utils import logger


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
    def _embedding_cache_key(text: str) -> str:
        text_hash = hashlib.md5(text.encode()).hexdigest()
        return f"embedding:{text_hash}"

    async def get_embedding(self, text: str) -> list[float]:
        key = self._embedding_cache_key(text)
        cached = await cache.get(key)
        if cached is not None:
            logger.debug(f"Cache hit for embedding: {key}")
            return cached

        try:
            response = await aembedding(
                model=settings.embedding_model,
                input=[text],
            )
            embedding = response.data[0]["embedding"]
            await cache.set(key, embedding, expire=CACHE_DEFAULT_TTL * 12)
            logger.debug(f"Generated embedding: {len(embedding)} dimensions")
            return embedding
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        keys = [self._embedding_cache_key(text) for text in texts]
        cached_results = await cache.get_many(*keys)

        results = []
        missing_indices = []
        missing_texts = []
        missing_keys = []

        for i, (text, key, cached) in enumerate(zip(texts, keys, cached_results, strict=False)):
            if cached is not None:
                results.append(cached)
            else:
                missing_indices.append(i)
                missing_texts.append(text)
                missing_keys.append(key)
                results.append(None)

        if missing_texts:
            try:
                response = await aembedding(
                    model=settings.embedding_model,
                    input=missing_texts,
                )
                new_embeddings = [item["embedding"] for item in response.data]

                for key, embedding in zip(missing_keys, new_embeddings, strict=False):
                    await cache.set(key, embedding, expire=CACHE_DEFAULT_TTL * 12)

                for i, embedding in zip(missing_indices, new_embeddings, strict=False):
                    results[i] = embedding

                logger.debug(f"Generated {len(new_embeddings)} embeddings")
            except Exception as e:
                logger.error(f"Batch embedding generation failed: {e}")
                raise

        return results
