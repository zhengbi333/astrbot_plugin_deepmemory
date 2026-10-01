from __future__ import annotations

import asyncio
import inspect
import math
import time
from datetime import datetime, timezone
from typing import Any

from .log import logger

from .config import ConfigView
from .models import MemoryRecord, SearchResult, SessionContext, clean_text
from .store import MemoryStore


async def maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _parse_dt(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)


class EmbeddingClient:
    """封装 Embedding Provider 的解析与调用。"""

    def __init__(self, context: Any, config: ConfigView, note_usage: Any = None):
        self.context = context
        self.config = config
        self.note_usage = note_usage  # 记账回调 note_usage(task, provider_id, prompt, out_tokens)

    def _timeout_ms(self) -> int:
        return max(0, self.config.int("retrieval.embedding_timeout_ms", 15000))

    async def resolve_provider(self) -> tuple[Any, str]:
        provider_id = clean_text(self.config.get("retrieval.embedding_provider_id", ""), 120)
        if provider_id:
            provider = await self._by_id(provider_id)
            if provider is not None:
                return provider, provider_id
        provider, found_id = await self._first()
        return provider, found_id

    async def _by_id(self, provider_id: str) -> Any | None:
        if self.context is None:
            return None
        getter = getattr(self.context, "get_embedding_provider_by_id", None) or getattr(
            self.context, "get_provider_by_id", None
        )
        if not callable(getter):
            return None
        try:
            return await maybe_await(getter(provider_id))
        except Exception as exc:
            logger.warning("[DeepMemory] 获取嵌入 Provider 失败: %s", exc)
            return None

    async def _first(self) -> tuple[Any | None, str]:
        if self.context is None:
            return None, ""
        manager = getattr(self.context, "provider_manager", None)
        candidates: list[Any] = []
        for getter_name in ("get_all_embedding_providers", "get_all_providers"):
            getter = getattr(self.context, getter_name, None)
            if callable(getter):
                try:
                    candidates = list(await maybe_await(getter()) or [])
                    break
                except Exception:
                    candidates = []
        if not candidates and manager is not None:
            for attr in ("embedding_provider_insts", "provider_insts"):
                candidates = getattr(manager, attr, None) or []
                if candidates:
                    break
        for provider in candidates:
            if not hasattr(provider, "get_embedding") and not hasattr(provider, "get_embeddings"):
                continue
            meta = self._meta_id(provider)
            return provider, meta
        return None, ""

    @staticmethod
    def _meta_id(provider: Any) -> str:
        try:
            meta = provider.meta()
            return str(getattr(meta, "id", "") or "")
        except Exception:
            return ""

    async def embed(self, text: str, *, provider: Any | None = None, provider_id: str = "") -> list[float]:
        text = clean_text(text, 1200)
        if not text:
            return []
        if provider is None:
            provider, provider_id = await self.resolve_provider()
        if provider is None:
            return []

        async def wait_result(value: Any) -> Any:
            if inspect.isawaitable(value):
                timeout_ms = self._timeout_ms()
                if timeout_ms > 0:
                    return await asyncio.wait_for(value, timeout=timeout_ms / 1000.0)
                return await value
            return value

        get_embedding = getattr(provider, "get_embedding", None)
        get_embeddings = getattr(provider, "get_embeddings", None)
        get_batch = getattr(provider, "get_embeddings_batch", None)
        try:
            if callable(get_embedding):
                payload = await wait_result(get_embedding(text))
                self._note("embed", provider_id, text)
                return self._coerce(payload)
            if callable(get_embeddings):
                payload = await wait_result(get_embeddings([text]))
                self._note("embed", provider_id, text)
                return self._first_vector(payload)
            if callable(get_batch):
                try:
                    payload = await wait_result(get_batch([text], batch_size=1, tasks_limit=1, max_retries=1))
                except TypeError:
                    payload = await wait_result(get_batch([text]))
                self._note("embed", provider_id, text)
                return self._first_vector(payload)
        except asyncio.TimeoutError:
            logger.warning("[DeepMemory] 嵌入调用超时: provider=%s", provider_id)
        except Exception as exc:
            logger.warning("[DeepMemory] 嵌入调用失败: provider=%s error=%s", provider_id, exc)
        return []

    def _note(self, task: str, provider_id: str, prompt: Any) -> None:
        if callable(self.note_usage):
            try:
                self.note_usage(task, provider_id or "default", prompt, 0)
            except Exception:
                pass

    def _coerce(self, value: Any) -> list[float]:
        if value is None:
            return []
        if isinstance(value, dict):
            for key in ("embedding", "vector"):
                if key in value:
                    vector = self._coerce(value.get(key))
                    if vector:
                        return vector
            for key in ("data", "embeddings", "vectors"):
                if key in value:
                    vector = self._coerce(value.get(key))
                    if vector:
                        return vector
            return []
        for attr in ("embedding", "vector", "data", "embeddings", "vectors"):
            if hasattr(value, attr):
                vector = self._coerce(getattr(value, attr, None))
                if vector:
                    return vector
        if isinstance(value, (list, tuple)):
            vector: list[float] = []
            for item in value:
                try:
                    vector.append(float(item))
                except Exception:
                    if isinstance(item, (list, tuple)) and item:
                        vector = self._coerce(item)
                    break
            return vector
        return []

    def _first_vector(self, payload: Any) -> list[float]:
        if isinstance(payload, dict):
            for key in ("data", "embeddings", "vectors"):
                if key in payload:
                    vector = self._first_vector(payload.get(key))
                    if vector:
                        return vector
        if isinstance(payload, (list, tuple)):
            for item in payload:
                if isinstance(item, dict) and ("embedding" in item or "vector" in item):
                    vector = self._coerce(item)
                    if vector:
                        return vector
            if payload:
                vector = self._coerce(payload[0])
                if vector:
                    return vector
        return self._coerce(payload)


class RerankClient:
    """封装 Rerank Provider 的解析与调用。"""

    def __init__(self, context: Any, config: ConfigView, note_usage: Any = None):
        self.context = context
        self.config = config
        self.note_usage = note_usage  # 记账回调 note_usage(task, provider_id, prompt, out_tokens)

    def _timeout_ms(self) -> int:
        return max(0, self.config.int("retrieval.rerank_timeout_ms", 2000))

    async def resolve_provider(self) -> tuple[Any | None, str]:
        provider_id = clean_text(self.config.get("retrieval.rerank_provider_id", ""), 120)
        if provider_id:
            provider = await self._by_id(provider_id)
            if provider is not None:
                return provider, provider_id
        manager = getattr(self.context, "provider_manager", None)
        candidates: list[Any] = []
        for getter_name in ("get_all_rerank_providers", "get_all_providers"):
            getter = getattr(self.context, getter_name, None)
            if callable(getter):
                try:
                    candidates = list(await maybe_await(getter()) or [])
                    break
                except Exception:
                    candidates = []
        if not candidates and manager is not None:
            for attr in ("rerank_provider_insts", "provider_insts"):
                candidates = getattr(manager, attr, None) or []
                if candidates:
                    break
        for provider in candidates:
            if hasattr(provider, "rerank"):
                return provider, self._meta_id(provider)
        return None, ""

    @staticmethod
    def _meta_id(provider: Any) -> str:
        try:
            meta = provider.meta()
            return str(getattr(meta, "id", "") or "")
        except Exception:
            return ""

    async def rerank(self, query: str, documents: list[str]) -> list[float] | None:
        if not documents:
            return None
        provider, provider_id = await self.resolve_provider()
        if provider is None:
            return None
        rerank = getattr(provider, "rerank", None)
        if not callable(rerank):
            return None
        started = time.monotonic()
        try:
            result = rerank(query, documents)
            if inspect.isawaitable(result):
                timeout_ms = self._timeout_ms()
                if timeout_ms > 0:
                    result = await asyncio.wait_for(result, timeout=timeout_ms / 1000.0)
                else:
                    result = await result
            scores = self._coerce_scores(result, len(documents))
            if scores is not None:
                if callable(self.note_usage):
                    try:
                        self.note_usage("rerank", provider_id or "default", query, 0)
                    except Exception:
                        pass
                logger.debug(
                    "[DeepMemory] 重排完成: provider=%s docs=%s elapsed_ms=%s",
                    provider_id, len(documents), int((time.monotonic() - started) * 1000),
                )
            return scores
        except asyncio.TimeoutError:
            logger.warning("[DeepMemory] 重排超时: provider=%s", provider_id)
        except Exception as exc:
            logger.warning("[DeepMemory] 重排失败: provider=%s error=%s", provider_id, exc)
        return None

    @staticmethod
    def _coerce_scores(payload: Any, expected: int) -> list[float] | None:
        if payload is None:
            return None
        if isinstance(payload, dict):
            for key in ("scores", "results"):
                if key in payload:
                    payload = payload.get(key)
                    break
            else:
                return None
        if not isinstance(payload, (list, tuple)) or len(payload) != expected:
            return None
        scores = [None] * expected
        indexed = any(isinstance(item, dict) and "index" in item for item in payload)
        if indexed and not all(isinstance(item, dict) and "index" in item for item in payload):
            return None
        for position, item in enumerate(payload):
            try:
                index = int(item["index"]) if indexed else position
                value = item.get("relevance_score", item.get("score")) if isinstance(item, dict) else item
                score = float(value)
            except (ValueError, TypeError, KeyError):
                return None
            if not 0 <= index < expected or scores[index] is not None or not math.isfinite(score):
                return None
            scores[index] = score
        return scores if all(score is not None for score in scores) else None



def visibility_filter(record: MemoryRecord, ctx: SessionContext, config: ConfigView) -> tuple[bool, str]:
    """判断记忆对当前会话是否可见，返回 (可见, 拒绝原因)。"""
    if record.lifecycle != "active":
        return False, "lifecycle_not_active"
    if record.persona_id and config.bool("isolation.persona_isolation_enabled", True):
        if record.persona_id != ctx.persona_id:
            return False, "persona_mismatch"
    min_confidence = config.float("weights.min_confidence", 0.1)
    if record.confidence < min_confidence:
        return False, "low_confidence"
    if record.scope == "public":
        if config.bool("isolation.public_memories_visible", True):
            return True, ""
        return False, "public_disabled"
    if record.scope == "private":
        if config.bool("isolation.user_isolation_enabled", True) and ctx.scope != "private":
            return False, "private_not_visible_from_group"
        if not ctx.user_id:
            return False, "missing_user"
        if not record.user_id and record.session_id and record.session_id != ctx.session_id:
            return False, "session_mismatch"
        if record.user_id and record.user_id != ctx.user_id:
            if config.bool("isolation.cross_user_visible", False):
                return True, ""
            return False, "user_isolation"
        return True, ""
    if record.scope == "group":
        if config.bool("isolation.group_isolation_enabled", True) and ctx.scope != "group":
            return False, "group_not_visible_from_private"
        if not ctx.group_id:
            return False, "missing_group"
        if not record.group_id and record.session_id and record.session_id != ctx.session_id:
            return False, "session_mismatch"
        if record.group_id and record.group_id != ctx.group_id:
            if config.bool("isolation.cross_group_visible", False):
                return True, ""
            return False, "group_isolation"
        return True, ""
    return False, "unknown_scope"


class RetrievalEngine:
    """混合检索：关键词 + 语义向量 + 重排 + 权重得分。"""

    def __init__(self, store: MemoryStore, config: ConfigView, context: Any, note_usage: Any = None):
        self.store = store
        self.config = config
        self.embedding = EmbeddingClient(context, config, note_usage)
        self.rerank = RerankClient(context, config, note_usage)

    # ------------------------------------------------------------------ scoring

    def _recency_factor(self, record: MemoryRecord) -> float:
        halflife_days = max(1, self.config.int("weights.recency_halflife_days", 30))
        try:
            dt = _parse_dt(record.created_at)
        except Exception:
            return 0.0
        age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
        if age_days <= 0:
            return 1.0
        return 0.5 ** (age_days / halflife_days)

    def _access_factor(self, record: MemoryRecord) -> float:
        cap = max(1, self.config.int("weights.access_count_cap", 10))
        return min(1.0, (record.access_count or 0) / cap)

    def _base_score(self, record: MemoryRecord) -> float:
        importance = record.importance if record.importance is not None else record.base_importance
        score = self.config.float("weights.base_importance_weight", 1.0) * importance
        score += self.config.float("weights.recency_weight", 0.25) * self._recency_factor(record)
        score += self.config.float("weights.access_weight", 0.15) * self._access_factor(record)
        return score

    # ------------------------------------------------------------------ retrieval

    async def search(
        self,
        query: str,
        ctx: SessionContext,
        top_k: int = 6,
        *,
        admin_read_all: bool = False,
    ) -> list[SearchResult]:
        top_k = max(1, min(50, int(top_k or 6)))
        keyword_weight = self.config.float("retrieval.keyword_weight", 0.6)
        embedding_enabled = self.config.bool("retrieval.embedding_enabled", False)
        embedding_weight = self.config.float("retrieval.embedding_weight", 0.55)

        fts_candidates = self.store.fts_search(query, limit=40)
        if len(fts_candidates) < 5:
            like_records = self.store.like_search(query, limit=30)
            fts_candidates = list(fts_candidates) + [(record, 0.35) for record in like_records]
        scored: dict[str, dict[str, Any]] = {}
        blocked: list[dict[str, Any]] = []

        def add(record: MemoryRecord, score: float, source: str) -> None:
            visible, reason = visibility_filter(record, ctx, self.config)
            if admin_read_all:
                visible, reason = True, ""
            if not visible:
                blocked.append({"id": record.id, "reason": reason, "content": clean_text(record.content, 120)})
                return
            item = scored.get(record.id)
            if item is None:
                scored[record.id] = {
                    "record": record,
                    "keyword": 0.0,
                    "embedding": 0.0,
                    "base": self._base_score(record),
                }
            item = scored[record.id]
            if source == "keyword":
                item["keyword"] = max(item["keyword"], score)
            elif source == "embedding":
                item["embedding"] = max(item["embedding"], score)

        for record, fts_score in fts_candidates:
            add(record, fts_score, "keyword")

        embedding_provider_id = ""
        query_vector: list[float] = []
        if embedding_enabled and ctx.persona_id:
            provider, embedding_provider_id = await self.embedding.resolve_provider()
            if provider is not None:
                query_vector = await self.embedding.embed(query, provider=provider, provider_id=embedding_provider_id)
                if query_vector:
                    # 0.79 性能修复：预池有序截断（重要度/新近优先）——读取行数与记忆总量无关，
                    # 低重要度旧记忆仍由 FTS 关键词通道兜底；候选池规模由配置控制。
                    pool_limit = max(
                        1, self.config.int("retrieval.embedding_candidate_limit", 800)
                    )
                    stored = self.store.iter_memory_embeddings(embedding_provider_id, limit=pool_limit)
                    limit = pool_limit
                    scored_vectors: list[tuple[MemoryRecord, float]] = []
                    for record, vector in stored[:limit]:
                        if not admin_read_all and not visibility_filter(record, ctx, self.config)[0]:
                            continue
                        if len(vector) != len(query_vector):
                            continue
                        sim = _cosine_similarity(query_vector, vector)
                        if sim >= self.config.float("retrieval.embedding_score_threshold", 0.34):
                            scored_vectors.append((record, sim))
                    scored_vectors.sort(key=lambda item: item[1], reverse=True)
                    merge_k = max(1, self.config.int("retrieval.embedding_top_k", 24))
                    for record, sim in scored_vectors[:merge_k]:
                        add(record, sim, "embedding")

        results: list[SearchResult] = []
        for record_id, item in scored.items():
            record: MemoryRecord = item["record"]
            final = item["base"] + keyword_weight * item["keyword"] + embedding_weight * item["embedding"]
            min_importance = self.config.float("weights.min_importance_for_injection", 0.0)
            reason = "keyword"
            if item["embedding"] > item["keyword"]:
                reason = "embedding"
            results.append(SearchResult(memory=record, score=final, reason=reason))
        results.sort(key=lambda r: r.score, reverse=True)

        mode = clean_text(self.config.get("retrieval.mode", "auto"), 20) or "auto"
        use_rerank = mode == "rerank"
        if mode == "auto" and embedding_enabled:
            use_rerank = True
        if use_rerank and results:
            candidate_limit = max(1, self.config.int("retrieval.rerank_candidate_limit", 32))
            top_candidates = results[:candidate_limit]
            documents = [r.memory.content for r in top_candidates]
            scores = await self.rerank.rerank(query, documents)
            if scores is not None:
                for item, score in zip(top_candidates, scores):
                    item.score = item.score * 0.4 + score * 1.2
                    item.reason = "rerank"
                top_candidates.sort(key=lambda r: r.score, reverse=True)
                remaining = [r for r in results if r.memory.id not in {c.memory.id for c in top_candidates}]
                results = top_candidates + remaining

        return results[:top_k]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
