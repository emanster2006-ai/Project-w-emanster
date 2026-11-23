"""Copy a Qdrant collection (vectors and payloads) to another Qdrant instance.

Used to publish the locally built index to Qdrant Cloud for the hosted demo without
re-embedding. Keys come from the environment, never from arguments:

    export TARGET_QDRANT_URL=https://<cluster>.cloud.qdrant.io:6333
    export TARGET_QDRANT_API_KEY=<key>
    python scripts/copy_collection.py financebench_eval150_ctx

The source defaults to the local stack (SOURCE_QDRANT_URL, default http://localhost:6333).
The target collection is recreated, so rerunning the script gives an exact copy.
"""

import os
import sys

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

# Small batches and a long timeout: free cloud clusters are slow to index large upserts.
BATCH = 64
TIMEOUT_S = 120


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    name = sys.argv[1]
    target_url = os.getenv("TARGET_QDRANT_URL")
    if not target_url:
        print("Set TARGET_QDRANT_URL (and TARGET_QDRANT_API_KEY for Qdrant Cloud).")
        return 2

    source = QdrantClient(
        url=os.getenv("SOURCE_QDRANT_URL", "http://localhost:6333"),
        api_key=os.getenv("SOURCE_QDRANT_API_KEY") or None,
    )
    target = QdrantClient(
        url=target_url,
        api_key=os.getenv("TARGET_QDRANT_API_KEY") or None,
        timeout=TIMEOUT_S,
    )

    info = source.get_collection(name)
    expected = source.count(name, exact=True).count
    if target.collection_exists(name):
        target.delete_collection(name)
    target.create_collection(name, vectors_config=info.config.params.vectors)

    copied, offset = 0, None
    while True:
        points, offset = source.scroll(
            name, limit=BATCH, offset=offset, with_payload=True, with_vectors=True
        )
        if points:
            target.upsert(
                name,
                points=[
                    PointStruct(id=p.id, vector=p.vector, payload=p.payload)
                    for p in points
                ],
                wait=True,
            )
            copied += len(points)
            print(f"copied {copied}/{expected}", flush=True)
        if offset is None:
            break

    actual = target.count(name, exact=True).count
    print(f"done: target has {actual} points (source {expected})")
    return 0 if actual == expected else 1


if __name__ == "__main__":
    sys.exit(main())
