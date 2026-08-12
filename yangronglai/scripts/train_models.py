"""Train and register all five XGBoost demonstration models."""

import argparse
import json

from app.config import settings
from app.engine.model_training import train_all


def main() -> int:
    parser = argparse.ArgumentParser(description="Train BankRisk-AI models")
    parser.add_argument("--size", type=int, default=3000, help="每个模型的合成样本数")
    args = parser.parse_args()
    if args.size < 500:
        parser.error("--size must be at least 500")
    registry = train_all(settings.MODEL_DIR, size=args.size)
    summary = {
        name: metadata["metrics"]
        for name, metadata in registry["models"].items()
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
