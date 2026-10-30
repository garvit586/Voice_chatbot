"""Reciprocal Rank Fusion — merges ranked lists into one."""

from __future__ import annotations

from typing import Any

K = 60  # RRF constant


def rrf(
    *ranked_lists: list[dict[str, Any]],
    id_field: str = "id",
    top_k: int = 20,
) -> list[dict[str, Any]]:
    scores: dict[Any, float] = {}
    by_id: dict[Any, dict[str, Any]] = {}

    for ranked in ranked_lists:
        for rank, item in enumerate(ranked):
            item_id = item[id_field]
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (K + rank + 1)
            by_id[item_id] = item

    merged = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return [by_id[item_id] for item_id, _ in merged]
