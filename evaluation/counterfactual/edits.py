"""Build the four arms of a counterfactual case from a captured context.

An arm is a list of regex substitutions applied to every captured chunk. The
hierarchical chunker stores overlapping chunks (2048/512/256 tokens), so the same
figure usually appears in several chunks; edits are applied to all of them. After
editing, a leak check fails the arm if any `gone` value is still present anywhere,
which is what makes "the evidence was removed" a checked claim rather than a hope.

Arms:
  A  original context, unedited
  B  the target figure replaced            → the answer should follow the edit
  C  an irrelevant figure replaced          → the answer should not change
  D  the supporting evidence removed        → the answer should abstain
"""

import hashlib
import json
import re

ARMS = ("A", "B", "C", "D")


class FixtureError(ValueError):
    """The manifest's edits do not apply cleanly to the captured context."""


def number_pattern(value: str) -> re.Pattern:
    """Match a figure not embedded in a longer number: '1,577' is not in '11,577'.

    Deliberately generous on the right ('1,577.0' and '1,577,000' count), because a
    leak check should err towards reporting a leak.
    """
    return re.compile(rf"(?<![\d.,]){re.escape(value)}(?!\d)")


def apply_ops(chunks: list[str], ops: list[dict]) -> list[str]:
    """Apply each {"re", "sub"} to every chunk; each op must change at least one."""
    out = list(chunks)
    for op in ops:
        pattern = re.compile(op["re"])
        total = 0
        for i, text in enumerate(out):
            out[i], n = pattern.subn(op.get("sub", ""), text)
            total += n
        if total == 0:
            raise FixtureError(f"edit matched nothing: {op['re']!r}")
    return out


def leaks(chunks: list[str], gone: list[str]) -> list[str]:
    """Values from `gone` that still appear in any chunk."""
    return [g for g in gone if any(number_pattern(g).search(c) for c in chunks)]


def build_arm(case: dict, captured_chunks: list[str], arm: str) -> list[str]:
    """Chunk texts for one arm, or FixtureError if the edit is not clean."""
    if arm == "A":
        return list(captured_chunks)
    spec = case["arms"][arm]
    edited = apply_ops(captured_chunks, spec["ops"])
    left = leaks(edited, spec.get("gone", []))
    if left:
        raise FixtureError(f"{case['id']} arm {arm}: still present after edit: {left}")
    for value in spec.get("present", []):  # e.g. the new figure in arm B
        if not leaks(edited, [value]):
            raise FixtureError(f"{case['id']} arm {arm}: expected {value!r} in context")
    return edited


def context_sha(chunks: list[str]) -> str:
    return hashlib.sha256(json.dumps(chunks).encode()).hexdigest()
