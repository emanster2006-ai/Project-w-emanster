.PHONY: help dev down ingest test eval eval-adversarial lint format clean setup

# ── Default ──────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  SecureRAG — Available Commands"
	@echo "  ─────────────────────────────"
	@echo "  make setup     Install all dependencies + spacy model"
	@echo "  make dev       Start full stack (Qdrant + Redis + API)"
	@echo "  make down      Stop all containers"
	@echo "  make ingest    Run data ingestion pipeline"
	@echo "  make test      Run unit + integration tests"
	@echo "  make eval      Run RAG evaluation harness (DeepEval)"
	@echo "  make eval-adv  Run adversarial red-team evaluation"
	@echo "  make ab-test   Run A/B pipeline comparison"
	@echo "  make lint      Run ruff linter"
	@echo "  make format    Auto-format with black + ruff"
	@echo "  make clean     Remove cache + temp files"
	@echo ""

# ── Setup ────────────────────────────────────────────────────────────────────
setup:
	pip install -r requirements.txt
	python -m spacy download en_core_web_lg
	cp -n .env.example .env || true
	@echo "✅ Setup complete. Edit .env with your API keys."

# ── Infrastructure ────────────────────────────────────────────────────────────
dev:
	docker-compose up --build -d
	@echo "✅ Stack running:"
	@echo "   API:    http://localhost:8000"
	@echo "   Qdrant: http://localhost:6333/dashboard"
	@echo "   Docs:   http://localhost:8000/docs"

down:
	docker-compose down

logs:
	docker-compose logs -f api

# ── Data Pipeline ─────────────────────────────────────────────────────────────
ingest:
	python scripts/ingest.py

golden:
	python scripts/generate_golden_dataset.py

finetune:
	python scripts/fine_tune_embeddings.py

# ── Testing ───────────────────────────────────────────────────────────────────
test:
	pytest tests/unit tests/integration -v --cov=. --cov-report=term-missing

eval:
	deepeval test run tests/eval/test_rag_quality.py -v

eval-adv:
	pytest tests/eval/test_adversarial.py -v

ab-test:
	python scripts/run_ab_test.py

# ── Code Quality ──────────────────────────────────────────────────────────────
lint:
	ruff check .

format:
	black .
	ruff check --fix .

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	rm -f eval_results.json
