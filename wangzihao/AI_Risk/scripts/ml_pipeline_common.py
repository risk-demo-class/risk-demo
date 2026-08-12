"""Shared Step 6 helpers for snapshot-based manufacturing ML data."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pymysql

from app.config import settings
from app.engine.ml_model import FEATURE_COLUMNS


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET_PATH = PROJECT_ROOT / "data" / "manufacturing_train_dataset.npz"
DEFAULT_MODEL_PATH = PROJECT_ROOT / settings.XGB_MODEL_PATH
POSITIVE_DECISIONS = {"人工审核", "拒绝"}


@dataclass(frozen=True)
class SnapshotDataset:
    X: np.ndarray
    y: np.ndarray
    groups: np.ndarray
    source_ids: np.ndarray
    event_ids: np.ndarray
    assessment_ids: np.ndarray
    event_types: np.ndarray
    missing_event_ids: tuple[str, ...]


def connect_mysql(db_name: str | None = None, *, autocommit: bool = False):
    """Use the same Settings fields as the application database layer."""
    return pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=db_name or settings.DB_NAME,
        charset="utf8mb4",
        autocommit=autocommit,
    )


def decision_to_label(decision: str) -> int:
    """Weak label: review/reject=1; pass/mark=0."""
    return int(decision in POSITIVE_DECISIONS)


def _load_features(cur, event_ids: list[str]) -> dict[str, dict[str, float]]:
    event_features: dict[str, dict[str, float]] = {}
    for offset in range(0, len(event_ids), 500):
        batch = event_ids[offset:offset + 500]
        placeholders = ",".join(["%s"] * len(batch))
        cur.execute(
            "SELECT event_id, feature_name, feature_value "
            f"FROM risk_feature WHERE event_id IN ({placeholders})",
            batch,
        )
        for event_id, feature_name, feature_value in cur.fetchall():
            features = event_features.setdefault(event_id, {})
            if feature_name in features:
                raise RuntimeError(
                    f"event {event_id} has duplicate feature snapshot: {feature_name}"
                )
            features[feature_name] = float(feature_value)
    return event_features


def load_snapshot_dataset(
    db_name: str | None = None,
    *,
    source_prefix: str = "ML",
    limit: int | None = None,
) -> SnapshotDataset:
    """Load complete 25-feature snapshots and rule-derived weak labels."""
    conn = connect_mysql(db_name)
    try:
        with conn.cursor() as cur:
            sql = """
                SELECT a.assessment_id, a.event_id, e.user_id,
                       e.event_source_id, e.event_type, a.decision
                FROM risk_assessment AS a
                JOIN risk_event AS e ON e.event_id = a.event_id
                WHERE e.event_source_id LIKE %s
                ORDER BY e.create_time, e.event_id
            """
            params: list[object] = [f"{source_prefix}%"]
            if limit is not None:
                sql += " LIMIT %s"
                params.append(int(limit))
            cur.execute(sql, params)
            rows = list(cur.fetchall())
            if not rows:
                raise RuntimeError(
                    f"no assessments found for source prefix {source_prefix!r}"
                )

            source_ids = [row[3] for row in rows]
            duplicate_sources = sorted(
                value for value, count in Counter(source_ids).items() if count > 1
            )
            if duplicate_sources:
                preview = ", ".join(duplicate_sources[:5])
                raise RuntimeError(f"duplicate business sources detected: {preview}")

            event_ids = [row[1] for row in rows]
            snapshots = _load_features(cur, event_ids)
    finally:
        conn.close()

    X_rows: list[list[float]] = []
    y_rows: list[int] = []
    groups: list[str] = []
    kept_sources: list[str] = []
    kept_events: list[str] = []
    assessments: list[str] = []
    event_types: list[str] = []
    missing: list[str] = []
    expected = set(FEATURE_COLUMNS)

    for assessment_id, event_id, dealer_id, source_id, event_type, decision in rows:
        features = snapshots.get(event_id, {})
        if len(features) != 25 or set(features) != expected:
            missing.append(event_id)
            continue
        vector = [features[name] for name in FEATURE_COLUMNS]
        if not np.isfinite(np.asarray(vector, dtype=np.float64)).all():
            raise RuntimeError(f"event {event_id} contains NaN or infinite feature values")
        X_rows.append(vector)
        y_rows.append(decision_to_label(decision))
        groups.append(dealer_id)
        kept_sources.append(source_id)
        kept_events.append(event_id)
        assessments.append(assessment_id)
        event_types.append(event_type)

    X = np.asarray(X_rows, dtype=np.float32)
    if X.ndim != 2 or X.shape[1] != len(FEATURE_COLUMNS):
        raise RuntimeError(f"training matrix must be (N, 25), got {X.shape}")
    y = np.asarray(y_rows, dtype=np.int8)
    if len(np.unique(y)) != 2:
        raise RuntimeError("weak labels must contain both label=0 and label=1")

    return SnapshotDataset(
        X=X,
        y=y,
        groups=np.asarray(groups, dtype=str),
        source_ids=np.asarray(kept_sources, dtype=str),
        event_ids=np.asarray(kept_events, dtype=str),
        assessment_ids=np.asarray(assessments, dtype=str),
        event_types=np.asarray(event_types, dtype=str),
        missing_event_ids=tuple(missing),
    )


def save_dataset(dataset: SnapshotDataset, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        X=dataset.X,
        y=dataset.y,
        groups=dataset.groups,
        source_ids=dataset.source_ids,
        event_ids=dataset.event_ids,
        assessment_ids=dataset.assessment_ids,
        event_types=dataset.event_types,
        feature_columns=np.asarray(FEATURE_COLUMNS, dtype=str),
    )
    return path


def load_dataset(path: str | Path) -> SnapshotDataset:
    with np.load(Path(path), allow_pickle=False) as payload:
        columns = payload["feature_columns"].tolist()
        if columns != FEATURE_COLUMNS:
            raise RuntimeError("dataset FEATURE_COLUMNS name/order differs from online inference")
        X = payload["X"].astype(np.float32)
        y = payload["y"].astype(np.int8)
        if X.ndim != 2 or X.shape[1] != 25 or not np.isfinite(X).all():
            raise RuntimeError(f"invalid training matrix: shape={X.shape}")
        return SnapshotDataset(
            X=X,
            y=y,
            groups=payload["groups"].astype(str),
            source_ids=payload["source_ids"].astype(str),
            event_ids=payload["event_ids"].astype(str),
            assessment_ids=payload["assessment_ids"].astype(str),
            event_types=payload["event_types"].astype(str),
            missing_event_ids=(),
        )


def vector_hashes(X: np.ndarray) -> set[str]:
    return {hashlib.sha256(row.tobytes()).hexdigest() for row in np.asarray(X, dtype=np.float32)}
