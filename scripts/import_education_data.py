# -*- coding: utf-8 -*-
"""
教育知识库一键导入脚本

用法：
    python scripts/import_education_data.py                      # 导入默认数据目录
    python scripts/import_education_data.py --data-root <路径>    # 指定数据目录
    python scripts/import_education_data.py --http http://127.0.0.1:8000  # 通过 HTTP 上传
    python scripts/import_education_data.py --dry-run             # 只列出待导入文件

默认数据目录优先级：
    1. 真实的《尚硅谷大模型项目实战之掌柜智库实战》教育数据（若存在）
    2. 本项目 data/demo 演示数据
"""
import argparse
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

SUPPORTED_EXTS = {".md", ".docx", ".pdf"}


def default_data_root() -> Path:
    candidates = [
        Path(r"D:\SGGLearning\14.尚硅谷大模型项目之掌柜智库\尚硅谷大模型项目实战之掌柜智库实战\资料\教育\数据"),
        PROJECT_ROOT / "data" / "demo",
        PROJECT_ROOT / "data",
    ]
    for cand in candidates:
        if cand.exists():
            return cand
    return candidates[-1]


def collect_files(data_root: Path):
    """收集待导入文件（课程介绍 / 题目资料 / 课程文档 / 项目文档）"""
    files = []
    for f in sorted(data_root.rglob("*")):
        if not f.is_file():
            continue
        if f.suffix.lower() not in SUPPORTED_EXTS:
            continue
        if "__pycache__" in f.parts:
            continue
        files.append(f)
    return files


def import_via_http(base_url: str, file_path: Path) -> str:
    """通过 HTTP 上传文件到导入服务"""
    import requests
    from edu_kb.import_process.nodes.node_entry import detect_content_type

    content_type = detect_content_type(file_path.stem, str(file_path))
    with open(file_path, "rb") as f:
        resp = requests.post(
            f"{base_url.rstrip('/')}/upload",
            files={"file": (file_path.name, f)},
            data={"content_type": content_type},
            timeout=60,
        )
    resp.raise_for_status()
    return resp.json().get("task_id", "")


def import_locally(file_path: Path, data_based_root_dir: Path) -> None:
    """本地直接调用 LangGraph 导入工作流"""
    from edu_kb.import_process.main_graph import KBImportWorkflow
    from edu_kb.tool.logger import logger

    task_id = str(uuid.uuid4())
    local_dir = (
        data_based_root_dir
        / datetime.now().strftime("%Y%m%d")
        / task_id
    )
    local_dir.mkdir(parents=True, exist_ok=True)

    init_state = {
        "task_id": task_id,
        "local_file_path": str(file_path),
        "local_dir": str(local_dir),
    }
    logger.info(f"开始导入：{file_path.name}（task_id={task_id}）")
    for chunk in KBImportWorkflow.create_and_run(init_state, stream=True):
        for node_name, node_result in chunk.items():
            logger.info(f"  [{node_name}] {str(node_result)[:200]}")
    logger.info(f"导入完成：{file_path.name}")


def main():
    parser = argparse.ArgumentParser(description="教育知识库一键导入")
    parser.add_argument("--data-root", type=str, default=None, help="教育数据根目录")
    parser.add_argument("--http", type=str, default=None, help="导入服务地址（如 http://127.0.0.1:8000）")
    parser.add_argument("--dry-run", action="store_true", help="仅列出待导入文件，不执行导入")
    args = parser.parse_args()

    data_root = Path(args.data_root) if args.data_root else default_data_root()
    print(f"数据目录：{data_root}")
    files = collect_files(data_root)
    print(f"待导入文件共 {len(files)} 个：")
    for f in files:
        print("  -", f.relative_to(data_root) if data_root in f.parents else f)

    if args.dry_run:
        return

    data_tmp = PROJECT_ROOT / "data" / "tmp"
    data_tmp.mkdir(parents=True, exist_ok=True)

    ok_count = 0
    fail_count = 0
    for f in files:
        try:
            if args.http:
                import_via_http(args.http, f)
            else:
                import_locally(f, data_tmp)
            ok_count += 1
        except Exception as e:
            fail_count += 1
            print(f"[失败] {f.name}: {e}")

    print(f"\n导入汇总：成功 {ok_count}，失败 {fail_count}，共 {len(files)}")
    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
