# SecureRAG frontend

Next.js 16 / React interface for the FastAPI backend. Displays answers, source passages, pipeline latency, decomposed questions, and API availability.

Run the backend on port 8000, then `npm ci` and `npm run dev`. Open http://localhost:3000. The default API target is http://localhost:8000; set the server-side `API_URL` at build time for a hosted backend. Query requests are proxied by Next.js and the server-side health indicator uses the same target. Never place provider keys in browser environment variables.

Validate with `npm run lint` and `npm run build`. This frontend was brought forward from the existing feat/frontend branch. A successful build does not verify a live retrieval query; that requires configured model providers and an ingested corpus.
