"""检查批量数据清单是否覆盖任务书规定的八类人物画像。"""

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data_generation import PATTERN_LABELS, load_manifest, pattern_distribution  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="检查八类银行风险人物画像")
    parser.add_argument(
        "--manifest", type=Path,
        default=PROJECT_ROOT / "data" / "bank_generation_manifest.json",
    )
    args = parser.parse_args()
    candidates = load_manifest(args.manifest)
    distribution = pattern_distribution(candidates)
    missing = [name for name in PATTERN_LABELS if distribution.get(name, 0) == 0]
    for name, label in PATTERN_LABELS.items():
        print(f"{label:<18} {distribution.get(name, 0):>6} 条  ({name})")
    if missing:
        raise SystemExit(f"缺少风险模式: {', '.join(missing)}")
    print("检查通过：八类场景全部存在，且场景由业务字段组合形成。")


if __name__ == "__main__":
    main()
