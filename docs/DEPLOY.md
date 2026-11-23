# Deploying a live demo

The demo has four pieces. The vector store, cache and frontend have free tiers; the API needs about 1.5 GB of RAM, which no free tier we found provides without a billing account. Check each provider's current limits before you start.

| Piece | Service | Why |
|---|---|---|
| Vector store | Qdrant Cloud (free cluster) | holds the indexed filing excerpts |
| Cache | Upstash Redis (free database) | semantic answer cache |
| API | Google Cloud Run (free monthly allowance; needs a billing account) **or** Hugging Face Spaces (Docker needs PRO) **or** Fly.io (paid) | runs FastAPI + the embedding and reranker models |
| Frontend | Vercel (Hobby) | Next.js UI; proxies `/api/v1/*` to the API |

**Sizing.** The API image installs CPU-only PyTorch and keeps `.git`, `frontend/`, `data/` and `.env` out through `.dockerignore`. Measured locally, the API uses about 2.5 GB of RAM with 2 workers once the models load. Run hosted demos with `UVICORN_WORKERS=1`. One worker uses about 1.5 GB, so 512 MB–1 GB free tiers (Render, Koyeb, Fly's small machines) run out of memory. As of Nov 2026, Hugging Face Docker Spaces require a PRO subscription.

**Cold starts.** The image sets `WARM_UP_MODELS=1`, so the reranker, BM25 index and PII models load at startup instead of on the first question, and the frontend proxy waits up to 120 s for the API. Hosts that scale to zero still need about two minutes to start a new instance, so the first visit after a quiet period is slow.

## 1. Qdrant Cloud

1. Create a free cluster and copy its URL and API key.
2. Copy the local index into it. This copies vectors and payloads as they are, so nothing is re-embedded and no LLM key is needed. With the local stack running (`make dev`) and the collection built:

   ```sh
   export TARGET_QDRANT_URL=https://<cluster>.cloud.qdrant.io:6333
   export TARGET_QDRANT_API_KEY=<key>
   docker cp scripts/copy_collection.py securerag_api:/tmp/
   docker exec -e SOURCE_QDRANT_URL=http://qdrant:6333 \
     -e TARGET_QDRANT_URL -e TARGET_QDRANT_API_KEY \
     securerag_api python /tmp/copy_collection.py financebench_eval150_ctx
   ```

   It ends with `done: target has 962 points (source 962)`. To build the collection from scratch instead, run `scripts/ingest.py` against the cluster.

## 2. Upstash Redis

Create a free Redis database and copy its `rediss://` URL. The API runs without Redis, but every question then costs a model call.

## 3. API

### Option A: Google Cloud Run

Within Cloud Run's free monthly allowance for a low-traffic demo; storing the ~5 GB image in Artifact Registry costs about $0.50/month. Requires a Google Cloud project with billing enabled.

1. Install the Google Cloud CLI and log in: `gcloud auth login`.
2. Put the keys in a private file (`chmod 600`), one `KEY=value` per line: `QDRANT_URL`, `QDRANT_API_KEY`, `REDIS_URL`, `GROQ_API_KEY`.
3. Deploy the committed code:

   ```sh
   scripts/deploy_cloud_run.sh <gcp-project-id> ~/securerag-cloud.env
   ```

   The script enables the needed APIs, stores the keys in Secret Manager, builds the image in Cloud Build (about 20 minutes; `.gcloudignore` keeps `.env`, `data/` and `frontend/` out of the upload) and deploys with 2 GiB, 1 worker, scale to zero and at most one instance. It prints the service URL.
4. Optional: set a budget alert in Billing → Budgets & alerts.

### Option B: Hugging Face Spaces (PRO)

1. Create a Space with the **Docker** SDK (blank template), for example `<user>/securerag-api`.
2. Log in once with `hf auth login`, then push the committed code:

   ```sh
   scripts/deploy_hf_space.sh <user>/securerag-api
   ```

   The script sends only what the API needs, with a Space README that sets `sdk: docker` and `app_port: 7860`. Rerun it after merging changes.
3. In the Space settings, add **variables**: `PORT=7860`, `UVICORN_WORKERS=1`, `QDRANT_COLLECTION_NAME=financebench_eval150_ctx`, `TOP_K_RERANK=8`, `LLM_MODEL=openai/gpt-oss-120b`, `CORS_ORIGINS=https://<your-app>.vercel.app`.
4. Add **secrets**: `GROQ_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `REDIS_URL`, and optionally `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`. Leave `INGEST_API_KEY` unset so the public demo cannot re-index.
5. The API URL is `https://<user>-securerag-api.hf.space`. Watch the build in the Space's **Logs** tab; `/health` answers once it is running.

### Option C: Fly.io (paid)

```sh
fly launch --no-deploy        # keeps fly.toml
fly secrets set GROQ_API_KEY=... QDRANT_URL=... QDRANT_API_KEY=... REDIS_URL=... CORS_ORIGINS=https://<your-app>.vercel.app
fly deploy
```

`fly.toml` already sets 1 worker, 2 GB and a `/health` check.

## 4. Frontend on Vercel

1. Import the GitHub repository and set the **root directory** to `frontend`.
2. Set `API_URL` to the API URL from step 3. It is read at **build** time, so redeploy after changing it.
3. Deploy and open the site; the header badge shows "API available" when the proxy reaches the API.

## 5. Verify

```sh
curl -s https://<api>/health
curl -s -X POST https://<api>/api/v1/query -H 'Content-Type: application/json' \
  -d '{"question":"What was the largest liability in American Express'"'"'s Balance Sheet in 2022?"}'
```

Then ask one of the example questions in the UI. Put the Vercel link in the README's Demo section once it works.

## Costs and limits

- Groq's free tier allows a limited number of tokens per minute and per day; each question uses several thousand. A public demo can exhaust it, and the API then returns 429 with `Retry-After`, which the UI shows as a countdown.
- `RATE_LIMIT_PER_MINUTE` (default 20 per IP) caps abuse of your Groq quota.
- Use a Groq key made for the demo, so it can be revoked without affecting anything else.
