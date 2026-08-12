"""一键完成制造业数据库初始化、数据生成和模型训练。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
for script in ("init_db.py","gen_training_data.py","train_xgb_model.py"):
    command=[sys.executable,str(ROOT/"scripts"/script)]
    print("执行："," ".join(command))
    subprocess.run(command,check=True)
