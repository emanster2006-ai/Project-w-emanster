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

## Operator endpoints and API hardening

- `POST /api/v1/ingest` requires `INGEST_API_KEY` as a bearer token (constant-time comparison) and is disabled when the key is unset. It refuses concurrent runs.
- API responses carry `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` and `Cache-Control: no-store`.
- CORS origins come from `CORS_ORIGINS` (default `http://localhost:3000`); set it explicitly in production.
- The semantic cache only reuses an answer when the years, figures and named entities in the question match and the request settings are identical.
- Known gap: the rate limiter keys on the client address, so behind a proxy or the Next.js rewrite all users share one bucket. Configure trusted forwarding headers before a public deployment.

## Scope

SecureRAG is a research/portfolio project. Its prompt-injection and PII controls
(see `docs/SECURITY.md`) are defense-in-depth measures, not a guarantee. Review
them before using this code with sensitive data.

## Known limitations of the input guard

`security/input_guard.py` is pattern-based. It normalizes Unicode (NFKC), strips zero-width characters and collapses whitespace before matching, so simple obfuscation is caught. It does **not** reliably catch paraphrased injections, other languages, base64/rot13 encodings, or indirect injection hidden in ingested documents. Treat it as one layer; on a small unseen attack set it blocked 1 of 8 (see `docs/BENCHMARKS.md`).

## Answer grounding

`security/grounding.py` compares the numbers in a generated answer with the retrieved context and logs a warning for any that do not appear. It is a heuristic (digits only, so unit conversions are flagged) and does not block or alter responses.

## Dependency vulnerabilities

- **Frontend:** `npm audit --audit-level=high` runs in CI and currently reports 0 vulnerabilities (Next.js 16.4.5).
- **Python:** `pip-audit` runs in CI as a report. As of 2026-11-20 GitHub's Dependabot flags `llama-index` / `llama-index-core`, `unstructured`, `pyarrow`, `black` and `pytest` at their pinned versions. Patched releases need a major migration (llama-index 0.11 to 0.13+, NumPy 1 to 2 for pyarrow) that has not been regression-tested against the retrieval benchmark, so those pins are deliberately left for a dedicated upgrade rather than bumped blind. `black` and `pytest` are development tools and are not in the runtime image.
- Dependabot is configured (`.github/dependabot.yml`) for npm, pip and GitHub Actions.
