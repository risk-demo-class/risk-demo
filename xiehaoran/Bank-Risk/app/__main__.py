"""支持 `python -m app` 启动 FastAPI (等价于 uvicorn app.main:app)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn

if __name__ == "__main__":
    # 端口 8010: 避免与基线 AI_Risk 的 8000 冲突
    uvicorn.run("app.main:app", host="0.0.0.0", port=8010, reload=False)
