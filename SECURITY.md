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
