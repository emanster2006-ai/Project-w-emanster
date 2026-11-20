# Security Policy

## Reporting a vulnerability

Please do not open a public issue for security problems. Use GitHub's
[private vulnerability reporting](../../security/advisories/new) for this
repository, and include steps to reproduce. You can expect an initial reply
within a few days.

## Handling secrets

- Never commit `.env` files or API keys. Only `.env.example` (placeholders) is tracked.
- If you believe a key was exposed, revoke and rotate it immediately.
- Secret scanning and push protection are enabled on this repository.

## Scope

SecureRAG is a research/portfolio project. Its prompt-injection and PII controls
(see `docs/SECURITY.md`) are defense-in-depth measures, not a guarantee. Review
them before using this code with sensitive data.

## Known limitations of the input guard

`security/input_guard.py` is pattern-based. It normalizes Unicode (NFKC), strips zero-width characters and collapses whitespace before matching, so simple obfuscation is caught. It does **not** reliably catch paraphrased injections, other languages, base64/rot13 encodings, or indirect injection hidden in ingested documents. Treat it as one layer; on a small unseen attack set it blocked 1 of 8 (see `docs/BENCHMARKS.md`).

## Answer grounding

`security/grounding.py` compares the numbers in a generated answer with the retrieved context and logs a warning for any that do not appear. It is a heuristic (digits only, so unit conversions are flagged) and does not block or alter responses.
