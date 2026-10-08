"""
Generate a synthetic golden dataset using Ragas.
Ragas uses an LLM teacher to create complex Q&A pairs from the corpus.
Run AFTER ingestion: python scripts/generate_golden_dataset.py
"""

import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def generate_golden_dataset(n_questions: int = 100):
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from ragas.testset.evolutions import multi_context, reasoning, simple
    from ragas.testset.generator import TestsetGenerator

    logger.info(f"Generating {n_questions} golden Q&A pairs via Ragas...")

    # Load a sample of raw docs for synthetic generation
    with open("data/raw_qa_pairs.json") as f:
        raw_pairs = json.load(f)

    # Use existing FinanceBench Q&A pairs as base (they're already ground truth)
    # AND generate additional synthetic ones via Ragas for harder multi-hop cases
    from llama_index.core import Document as LIDoc

    docs = [
        LIDoc(
            text=p.get("answer", ""),
            metadata={
                "question": p["question"],
                "company": p.get("company"),
                "year": p.get("year"),
            },
        )
        for p in raw_pairs[:200]  # use first 200 as source material
    ]

    generator_llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY"))
    critic_llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY"))
    embeddings = OpenAIEmbeddings(api_key=os.getenv("OPENAI_API_KEY"))

    generator = TestsetGenerator.from_langchain(
        generator_llm=generator_llm,
        critic_llm=critic_llm,
        embeddings=embeddings,
    )

    # Mix of question types: simple (40%), reasoning (40%), multi-context (20%)
    testset = generator.generate_with_llama_index_docs(
        docs,
        test_size=n_questions,
        distributions={simple: 0.4, reasoning: 0.4, multi_context: 0.2},
    )

    df = testset.to_pandas()

    # Merge with original FinanceBench ground truth
    golden = df.to_dict(orient="records")

    os.makedirs("evaluation", exist_ok=True)
    with open("evaluation/golden_dataset.json", "w") as f:
        json.dump(golden, f, indent=2)

    logger.info(
        f"Saved {len(golden)} golden Q&A pairs to evaluation/golden_dataset.json"
    )
    return golden


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=100)
    args = parser.parse_args()
    generate_golden_dataset(n_questions=args.n)
