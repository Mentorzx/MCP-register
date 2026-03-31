from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path
from uuid import uuid4

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE_ROOT))
sys.path.insert(0, str(WORKSPACE_ROOT / "src"))

from mcp_crm.slices.users.application.user_service import UserService  # noqa: E402
from tests.support import build_embedder, build_repo  # noqa: E402


def _description_for_index(index: int) -> str:
    topics = [
        "machine learning platform",
        "enterprise sales operations",
        "wealth management advisory",
        "industrial robotics maintenance",
        "logistics planning and routing",
        "animal health compliance",
        "pharmaceutical quality assurance",
        "retail demand forecasting",
    ]
    region = ["norte", "sul", "leste", "oeste"][index % 4]
    detail = index // len(topics)
    return f"{topics[index % len(topics)]} batch {detail} {region}"


def _measure_ms(callable_obj, *, runs: int) -> list[float]:
    durations: list[float] = []
    for _ in range(runs):
        started = time.perf_counter()
        callable_obj()
        durations.append((time.perf_counter() - started) * 1000)
    return durations


def _build_dataset(
    runtime_root: Path,
    *,
    size: int,
) -> UserService:
    db_name = f"benchmark-{size}"
    repo = build_repo(runtime_root, name=db_name)
    embedder = build_embedder()
    service = UserService(repo, embedder)
    for index in range(size):
        description = _description_for_index(index)
        repo.create_user(
            name=f"U{index}",
            email=f"u{index}@example.com",
            description=description,
            embedding=embedder.embed(description),
        )
    return service


def _p95(values: list[float]) -> float:
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[94]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark simples da busca vetorial SQLite."
    )
    parser.add_argument(
        "--size", type=int, default=10000, help="Quantidade de registros."
    )
    parser.add_argument(
        "--top-k", type=int, default=10, help="Quantidade de resultados."
    )
    parser.add_argument(
        "--warm-runs",
        type=int,
        default=5,
        help="Numero de buscas de aquecimento.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=20,
        help="Numero de buscas medidas.",
    )
    parser.add_argument(
        "--query",
        default="industrial robotics maintenance oeste",
        help="Consulta usada no benchmark.",
    )
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="mcp-search-bench-") as tmp_dir:
        runtime_root = Path(tmp_dir)

        started = time.perf_counter()
        service = _build_dataset(runtime_root, size=args.size)
        import_ms = (time.perf_counter() - started) * 1000

        query = args.query

        def search():
            return service.search_users(query=query, top_k=args.top_k)

        first_run_ms = _measure_ms(search, runs=1)[0]
        _measure_ms(search, runs=args.warm_runs)

        measured = _measure_ms(search, runs=args.runs)
        tracemalloc.start()
        search()
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        write_started = time.perf_counter()
        service.create_user(
            name="Tail User",
            email=f"tail+{uuid4().hex[:8]}@example.com",
            description="industrial robotics maintenance expansion oeste",
        )
        write_ms = (time.perf_counter() - write_started) * 1000
        post_write_search_ms = _measure_ms(search, runs=1)[0]

    report = {
        "dataset_size": args.size,
        "top_k": args.top_k,
        "query": query,
        "import_ms": round(import_ms, 3),
        "first_search_ms": round(first_run_ms, 3),
        "write_ms": round(write_ms, 3),
        "post_write_search_ms": round(post_write_search_ms, 3),
        "warm_search_ms": {
            "min": round(min(measured), 3),
            "median": round(statistics.median(measured), 3),
            "p95": round(_p95(measured), 3),
            "max": round(max(measured), 3),
        },
        "peak_memory_mb": round(peak_bytes / (1024 * 1024), 3),
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
