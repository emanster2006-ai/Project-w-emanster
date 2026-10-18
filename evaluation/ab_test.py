"""
A/B test pipeline configuration manager.
Defines the 5 pipeline configs and utilities for setting runtime flags.
The actual test runner lives in scripts/run_ab_test.py.
"""

import os
from dataclasses import dataclass


@dataclass
class PipelineConfig:
    name: str
    hyde: bool
    rerank: bool
    hybrid: bool
    description: str = ""

    def apply(self) -> None:
        """Set environment flags for this config (used by run_ab_test.py)."""
        os.environ["ENABLE_HYDE"] = str(self.hyde).lower()
        os.environ["ENABLE_HYBRID_RETRIEVAL"] = str(self.hybrid).lower()
        # Reranking flag checked at call site in run_ab_test.py

    def as_label(self) -> str:
        parts = []
        if self.hybrid:
            parts.append("Hybrid")
        else:
            parts.append("Dense")
        if self.hyde:
            parts.append("HyDE")
        if self.rerank:
            parts.append("Rerank")
        return " + ".join(parts) if parts else self.name


PIPELINE_CONFIGS = [
    PipelineConfig(
        name="baseline_dense_only",
        hyde=False,
        rerank=False,
        hybrid=False,
        description="Naive RAG: dense retrieval only, no reranking, no HyDE",
    ),
    PipelineConfig(
        name="dense_plus_rerank",
        hyde=False,
        rerank=True,
        hybrid=False,
        description="Dense retrieval + CrossEncoder reranking",
    ),
    PipelineConfig(
        name="hybrid_only",
        hyde=False,
        rerank=False,
        hybrid=True,
        description="Hybrid (dense + BM25 + RRF), no reranking",
    ),
    PipelineConfig(
        name="hybrid_plus_rerank",
        hyde=False,
        rerank=True,
        hybrid=True,
        description="Hybrid retrieval + CrossEncoder reranking",
    ),
    PipelineConfig(
        name="hyde_plus_hybrid_rerank",
        hyde=True,
        rerank=True,
        hybrid=True,
        description="Full stack: HyDE + hybrid retrieval + CrossEncoder reranking",
    ),
]

# Convenience lookup
CONFIGS_BY_NAME = {c.name: c for c in PIPELINE_CONFIGS}
