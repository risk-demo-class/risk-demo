from __future__ import annotations


def predict_risk(features: dict[str, float]) -> float:
    """Deterministic baseline until a versioned production model is registered."""
    screening = features.get("user_screening_match_score", 0.0)
    device = max(
        features.get("device_is_emulator", 0.0),
        features.get("device_is_rooted", 0.0),
    )
    amount = min(features.get("transaction_amount", 0.0) / 10_000, 1.0)
    return min(1.0, screening * 0.7 + device * 0.2 + amount * 0.1)

