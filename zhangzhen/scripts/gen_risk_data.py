"""兼容入口：风险评估数据统一由跨日期真实回放脚本生成。"""

from scripts.gen_risk_data_with_dates import build_parser, run

import asyncio


if __name__ == "__main__":
    asyncio.run(run(build_parser().parse_args()))
