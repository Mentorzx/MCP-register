from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE_ROOT))
sys.path.insert(0, str(WORKSPACE_ROOT / "src"))

from mcp_crm.slices.users.application.user_service import UserService  # noqa: E402
from mcp_crm.slices.users.infrastructure.embeddings import (  # noqa: E402
    DeterministicTestEmbedder,
    SentenceTransformerEmbedder,
)
from tests.support import build_repo  # noqa: E402

DEFAULT_FIXTURE = WORKSPACE_ROOT / "tests" / "fixtures" / "search_quality_cases.json"
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def _build_embedder(provider: str, model: str):
    normalized = provider.strip().lower()
    if normalized == "deterministic":
        return DeterministicTestEmbedder()
    if normalized in {"sentence-transformer", "sentence-transformers", "local"}:
        return SentenceTransformerEmbedder(model)
    raise ValueError(f"unsupported provider: {provider}")


def _load_fixture(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _seed_dataset(
    runtime_root: Path,
    *,
    fixture: dict[str, object],
    provider: str,
    model: str,
) -> tuple[UserService, dict[str, int]]:
    repo = build_repo(runtime_root, name=f"quality-{provider}")
    embedder = _build_embedder(provider, model)
    service = UserService(repo, embedder)
    key_to_id: dict[str, int] = {}

    for user in _as_list(fixture.get("users")):
        if not isinstance(user, dict):
            continue
        user_id = service.create_user(
            name=str(user["name"]),
            email=str(user["email"]),
            description=str(user["description"]),
        )
        key_to_id[str(user["key"])] = user_id

    return service, key_to_id


def _recall_at_k(predicted: list[int], relevant: set[int], *, k: int) -> float:
    if not relevant:
        return 0.0
    hits = sum(1 for value in predicted[:k] if value in relevant)
    return hits / len(relevant)


def _mrr(predicted: list[int], relevant: set[int]) -> float:
    for index, value in enumerate(predicted, start=1):
        if value in relevant:
            return 1.0 / index
    return 0.0


def _ndcg_at_k(predicted: list[int], relevant: set[int], *, k: int) -> float:
    gains = [1.0 if value in relevant else 0.0 for value in predicted[:k]]
    dcg = sum(gain / math.log2(index + 2) for index, gain in enumerate(gains))
    ideal_hits = min(len(relevant), k)
    ideal = sum(1.0 / math.log2(index + 2) for index in range(ideal_hits))
    return dcg / ideal if ideal else 0.0


def _summarize(bucket: list[dict[str, float]]) -> dict[str, float]:
    if not bucket:
        return {
            "count": 0.0,
            "recall_at_1": 0.0,
            "recall_at_3": 0.0,
            "recall_at_5": 0.0,
            "mrr": 0.0,
            "ndcg_at_5": 0.0,
        }
    count = float(len(bucket))
    return {
        "count": count,
        "recall_at_1": round(sum(item["recall_at_1"] for item in bucket) / count, 6),
        "recall_at_3": round(sum(item["recall_at_3"] for item in bucket) / count, 6),
        "recall_at_5": round(sum(item["recall_at_5"] for item in bucket) / count, 6),
        "mrr": round(sum(item["mrr"] for item in bucket) / count, 6),
        "ndcg_at_5": round(sum(item["ndcg_at_5"] for item in bucket) / count, 6),
    }


def _evaluate(
    service: UserService,
    *,
    fixture: dict[str, object],
    key_to_id: dict[str, int],
    top_k: int,
) -> dict[str, object]:
    per_type: dict[str, list[dict[str, float]]] = defaultdict(list)
    overall: list[dict[str, float]] = []
    misses: list[dict[str, object]] = []

    for query_case in _as_list(fixture.get("queries")):
        if not isinstance(query_case, dict):
            continue

        results = service.search_users(query=str(query_case["query"]), top_k=top_k)
        predicted = [item.id for item in results]
        relevant = {
            key_to_id[str(key)] for key in _as_list(query_case.get("relevant_keys"))
        }

        metrics = {
            "recall_at_1": _recall_at_k(predicted, relevant, k=1),
            "recall_at_3": _recall_at_k(predicted, relevant, k=min(3, top_k)),
            "recall_at_5": _recall_at_k(predicted, relevant, k=min(5, top_k)),
            "mrr": _mrr(predicted, relevant),
            "ndcg_at_5": _ndcg_at_k(predicted, relevant, k=min(5, top_k)),
        }
        overall.append(metrics)
        per_type[str(query_case["type"])].append(metrics)

        if metrics["recall_at_1"] == 0.0:
            misses.append(
                {
                    "name": str(query_case["name"]),
                    "type": str(query_case["type"]),
                    "query": str(query_case["query"]),
                    "relevant_ids": sorted(relevant),
                    "top_results": [
                        {
                            "id": item.id,
                            "name": item.name,
                            "score": item.score,
                        }
                        for item in results[:5]
                    ],
                }
            )

    return {
        "overall": _summarize(overall),
        "by_type": {
            name: _summarize(bucket) for name, bucket in sorted(per_type.items())
        },
        "misses": misses,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Avalia qualidade de busca com um conjunto curado de consultas."
    )
    parser.add_argument(
        "--provider",
        choices=["deterministic", "sentence-transformers"],
        default="deterministic",
        help="Provider de embedding usado na avaliacao.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Modelo sentence-transformers usado quando o provider for real.",
    )
    parser.add_argument(
        "--fixture",
        default=str(DEFAULT_FIXTURE),
        help="Arquivo JSON com usuarios e consultas relevantes.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Quantidade de resultados avaliados por consulta.",
    )
    args = parser.parse_args()

    fixture_path = Path(args.fixture)
    fixture = _load_fixture(fixture_path)

    with tempfile.TemporaryDirectory(prefix="mcp-quality-") as tmp_dir:
        service, key_to_id = _seed_dataset(
            Path(tmp_dir),
            fixture=fixture,
            provider=args.provider,
            model=args.model,
        )
        report = _evaluate(
            service,
            fixture=fixture,
            key_to_id=key_to_id,
            top_k=args.top_k,
        )

    print(
        json.dumps(
            {
                "provider": args.provider,
                "model": (
                    args.model if args.provider != "deterministic" else "deterministic"
                ),
                "fixture": str(fixture_path),
                "top_k": args.top_k,
                **report,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
