# Deploying a live demo

The demo has four pieces. Every one has a free tier, but check each provider's current limits before you start.

| Piece | Service | Why |
|---|---|---|
| Vector store | Qdrant Cloud (free cluster) | holds the indexed filing excerpts |
| Cache | Upstash Redis (free database) | semantic answer cache |
| API | Hugging Face Spaces (Docker, free CPU) **or** Fly.io (paid) | runs FastAPI + the embedding and reranker models |
| Frontend | Vercel (Hobby) | Next.js UI; proxies `/api/v1/*` to the API |

**Sizing.** Measured locally, the API uses about 2.5 GB of RAM with 2 workers once the models load, and the image is about 15 GB. Run hosted demos with `UVICORN_WORKERS=1`. Fly's free-size machines (1 GB) run out of memory, so Fly needs a paid 2 GB+ machine; a free Hugging Face CPU Space has enough memory.

## 1. Qdrant Cloud

1. Create a free cluster and copy its URL and API key.
2. Ingest from your machine into it (embeddings run locally, no LLM key needed):

   ```sh
   export QDRANT_URL=https://<cluster>.cloud.qdrant.io:6333
   export QDRANT_API_KEY=<key>
   export QDRANT_COLLECTION_NAME=financebench
   python scripts/ingest.py
   ```

3. Check it: `make retrieval-bench` against the same variables should report the numbers in [BENCHMARKS.md](BENCHMARKS.md).

## 2. Upstash Redis

Create a free Redis database and copy its `rediss://` URL. The API runs without Redis, but every question then costs a model call.

## 3. API

### Option A: Hugging Face Spaces (free)

1. Create a Space with the **Docker** SDK.
2. Push this repository to the Space (or connect it to GitHub). Add this header to the Space's `README.md`:

   ```yaml
   ---
   title: SecureRAG API
   sdk: docker
   app_port: 7860
   ---
   ```

3. In the Space settings, add **variables**: `PORT=7860`, `UVICORN_WORKERS=1`, `QDRANT_COLLECTION_NAME=financebench`, `LLM_MODEL=openai/gpt-oss-120b`, `CORS_ORIGINS=https://<your-app>.vercel.app`.
4. Add **secrets**: `GROQ_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `REDIS_URL`, and optionally `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`. Leave `INGEST_API_KEY` unset so the public demo cannot re-index.
5. The API URL is `https://<user>-<space>.hf.space`. Free Spaces sleep when idle, so the first request after a pause is slow.

### Option B: Fly.io (paid)

```sh
fly launch --no-deploy        # keeps fly.toml
fly secrets set GROQ_API_KEY=... QDRANT_URL=... QDRANT_API_KEY=... REDIS_URL=... CORS_ORIGINS=https://<your-app>.vercel.app
fly deploy
```

`fly.toml` already sets 1 worker, 2 GB and a `/health` check.

## 4. Frontend on Vercel

1. Import the repository and set the **root directory** to `frontend`.
2. Set `API_URL` to the API URL from step 3. It is read at **build** time, so redeploy after changing it.
3. Deploy and open the site; the header badge shows "API available" when the proxy reaches the API.

## 5. Verify

```sh
curl -s https://<api>/health
curl -s -X POST https://<api>/api/v1/query -H 'Content-Type: application/json' \
  -d '{"question":"What is the FY2019 fixed asset turnover ratio for Activision Blizzard?"}'
```

Then ask one of the example questions in the UI. Put the Vercel link in the README's Demo section once it works.

## Costs and limits

- Groq's free tier allows a limited number of tokens per minute and per day; each question uses several thousand. A public demo can exhaust it, and the API then returns 429 with `Retry-After`, which the UI shows as a countdown.
- `RATE_LIMIT_PER_MINUTE` (default 20 per IP) caps abuse of your Groq quota.
