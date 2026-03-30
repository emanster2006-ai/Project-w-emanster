"""
Output validation using instructor + Pydantic.
OWASP LLM02 mitigation — enforces structured, schema-compliant LLM outputs.
"""

import instructor
from pydantic import BaseModel, Field, field_validator
import re
import logging

logger = logging.getLogger(__name__)


class FinancialRAGResponse(BaseModel):
    """
    Schema that all LLM outputs must conform to.
    instructor re-prompts automatically if the LLM fails to comply.
    """
    answer: str = Field(..., description="Direct answer to the financial question")
    confidence: str = Field(..., pattern="^(high|medium|low)$")
    requires_professional_advice: bool = Field(
        default=False,
        description="True if question requires CPA/financial advisor"
    )

    @field_validator("answer")
    @classmethod
    def no_hallucination_phrases(cls, v: str) -> str:
        """Catch common hallucination tells."""
        red_flags = [
            "as an AI",
            "I don't have access to",
            "I cannot verify",
            "based on my training",
        ]
        for flag in red_flags:
            if flag.lower() in v.lower():
                raise ValueError(f"Answer contains hallucination indicator: '{flag}'")
        return v

    @field_validator("answer")
    @classmethod
    def no_competitor_data(cls, v: str) -> str:
        """Prevent leaking info about companies not in retrieved context."""
        # This is a placeholder — extend with your corpus's company list
        return v
