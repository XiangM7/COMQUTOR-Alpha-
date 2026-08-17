"""Offline, unintegrated LLM semantic-runtime contract foundation."""

from comqutor_alpha.llm_runtime.cache import (
    LLM_CACHE_KEY_VERSION,
    LLMResponseCache,
    NullLLMResponseCache,
    RedisLLMResponseCache,
    build_llm_cache_key,
)
from comqutor_alpha.llm_runtime.canonical_json import (
    canonical_json_bytes,
    canonical_json_text,
    sha256_bytes,
    sha256_canonical_json,
    sha256_text,
)
from comqutor_alpha.llm_runtime.contracts import (
    LLM_CACHE_ENTRY_SCHEMA_VERSION,
    SEMANTIC_CALL_SCHEMA_VERSION,
    CacheMetadata,
    LLMCacheEntry,
    SemanticCallRecord,
    TokenUsage,
    cache_entry_from_record,
    redact_sensitive_text,
    validate_cache_entry,
    validate_semantic_call_record,
    validate_semantic_call_records,
)
from comqutor_alpha.llm_runtime.manifest import (
    SEMANTIC_MANIFEST_FILENAME,
    SEMANTIC_MANIFEST_SCHEMA_VERSION,
    build_semantic_manifest,
    verify_semantic_manifest,
    write_semantic_manifest_atomic,
)
from comqutor_alpha.llm_runtime.recorder import (
    SEMANTIC_CALLS_FILENAME,
    SemanticCallRecorder,
)
from comqutor_alpha.llm_runtime.session import (
    UNKNOWN_PROVIDER_OR_MODEL,
    SemanticCallStart,
    SemanticCallTrace,
    SemanticRuntimeSession,
)

__all__ = [
    "LLM_CACHE_ENTRY_SCHEMA_VERSION",
    "LLM_CACHE_KEY_VERSION",
    "SEMANTIC_CALLS_FILENAME",
    "SEMANTIC_CALL_SCHEMA_VERSION",
    "SEMANTIC_MANIFEST_FILENAME",
    "SEMANTIC_MANIFEST_SCHEMA_VERSION",
    "CacheMetadata",
    "LLMCacheEntry",
    "LLMResponseCache",
    "NullLLMResponseCache",
    "RedisLLMResponseCache",
    "SemanticCallRecord",
    "SemanticCallRecorder",
    "SemanticCallStart",
    "SemanticCallTrace",
    "SemanticRuntimeSession",
    "TokenUsage",
    "UNKNOWN_PROVIDER_OR_MODEL",
    "build_llm_cache_key",
    "build_semantic_manifest",
    "cache_entry_from_record",
    "canonical_json_bytes",
    "canonical_json_text",
    "redact_sensitive_text",
    "sha256_bytes",
    "sha256_canonical_json",
    "sha256_text",
    "validate_cache_entry",
    "validate_semantic_call_record",
    "validate_semantic_call_records",
    "verify_semantic_manifest",
    "write_semantic_manifest_atomic",
]
