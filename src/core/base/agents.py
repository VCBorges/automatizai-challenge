from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langfuse import Langfuse
from langfuse import get_client as get_langfuse_client
from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler

from src.core.settings import get_settings

settings = get_settings()

if settings.LANGFUSE_ENABLED:
    Langfuse(
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        secret_key=settings.LANGFUSE_SECRET_KEY,
        host=settings.LANGFUSE_BASE_URL,
    )
    langfuse = get_langfuse_client()


def build_langfuse_callback() -> LangfuseCallbackHandler:
    return LangfuseCallbackHandler(
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        update_trace=True,
    )


def build_runnable_config(correlation_id: str | None = None) -> RunnableConfig:
    callbacks = []
    if settings.LANGFUSE_ENABLED:
        callbacks.append(build_langfuse_callback())

    metadata: dict[str, str | None] = {}
    if correlation_id:
        metadata["correlation_id"] = correlation_id
        # Langfuse 3 uses metadata keys for session/trace info
        metadata["langfuse_session_id"] = correlation_id
        metadata["langfuse_trace_name"] = f"agent-{correlation_id}"

    return RunnableConfig(
        run_id=correlation_id,
        metadata=metadata,
        callbacks=callbacks,
    )


def build_llm(correlation_id: str | None = None) -> ChatOpenAI:
    callbacks = None
    if settings.LANGFUSE_ENABLED:
        callbacks = [build_langfuse_callback()]

    return ChatOpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_API_BASE_URL,
        model=settings.OPENROUTER_MODEL,
        temperature=settings.OPENROUTER_TEMPERATURE,
        reasoning_effort="low",
        callbacks=callbacks,
    )


def truncate_text(text: str, *, max_chars: int = 6000) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def limit_list(items: list[str], *, max_items: int = 3) -> list[str]:
    if max_items <= 0:
        return []
    return list(items[:max_items])
