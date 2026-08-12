# -*- coding: utf-8 -*-
"""只导入课程介绍 + 题库（核心数据），供完整数据导入前的快速验证使用"""
import sys
import uuid
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATA_ROOT = Path(r"D:\SGGLearning\14.尚硅谷大模型项目之掌柜智库\尚硅谷大模型项目实战之掌柜智库实战\资料\教育\数据")
FILES = ["课程介绍.md", "题目资料.md"]


def main():
    from edu_kb.import_process.main_graph import KBImportWorkflow
    from edu_kb.tool.logger import logger

    out_root = PROJECT_ROOT / "data" / "tmp" / "core_import"
    out_root.mkdir(parents=True, exist_ok=True)

    ok = 0
    for name in FILES:
        src = DATA_ROOT / name
        if not src.exists():
            logger.error(f"文件不存在: {src}")
            continue
        task_id = str(uuid.uuid4())
        local_dir = out_root / datetime.now().strftime("%Y%m%d") / task_id
        local_dir.mkdir(parents=True, exist_ok=True)
        init_state = {
            "task_id": task_id,
            "local_file_path": str(src),
            "local_dir": str(local_dir),
        }
        try:
            logger.info(f"开始导入: {name} (task={task_id})")
            for chunk in KBImportWorkflow.create_and_run(init_state, stream=True):
                for node_name, node_result in chunk.items():
                    logger.info(f"  [{node_name}] {str(node_result)[:120]}")
            logger.info(f"完成: {name}")
            ok += 1
        except Exception as e:
            logger.exception(f"失败: {name}: {e}")
    logger.info(f"核心数据导入汇总: 成功 {ok}/{len(FILES)}")
    sys.exit(0 if ok == len(FILES) else 1)


if __name__ == "__main__":
    main()