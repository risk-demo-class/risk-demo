# -*- coding: utf-8 -*-
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import uvicorn
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, Form
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse

from edu_kb.config.config import file_upload_config, minio_config
from edu_kb.config.constants import CONTENT_TYPE_CN
from edu_kb.import_process.main_graph import KBImportWorkflow
from edu_kb.import_process.nodes.node_entry import detect_content_type
from edu_kb.tool.logger import logger
from edu_kb.utils.minio_utils import get_minio_client
from edu_kb.utils.task_utils import (
    add_running_task,
    add_done_task,
    get_task_info,
    update_task_status,
    TASK_STATUS_PROCESSING,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
)

app = FastAPI(
    title="教育知识库：内容导入",
    description="教育知识库内容导入相关接口（课程资料 / 项目文档 / 讲义 / 题库）",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/import.html")
async def get_import_page():
    html_path = Path(__file__).absolute().parent.parent / "page" / "import.html"
    return FileResponse(html_path)


def run_graph_task(task_id, local_dir, local_file_path):
    """后台任务：执行导入工作流"""
    try:
        update_task_status(task_id, TASK_STATUS_PROCESSING)
        init_state = {
            "task_id": task_id,
            "local_file_path": local_file_path,
            "local_dir": local_dir,
        }
        for chunk in KBImportWorkflow.create_and_run(init_state, stream=True):
            for node_name, node_result in chunk.items():
                logger.info(f"{node_name}: {node_result}")
        update_task_status(task_id, TASK_STATUS_COMPLETED)
    except Exception as e:
        update_task_status(task_id, TASK_STATUS_FAILED)
        logger.error(f"{task_id} : 任务执行失败: {e}", exc_info=True)


def _resolve_upload_root() -> str:
    """解析上传文件落地根目录；未配置时回退到项目 data/tmp/upload"""
    if file_upload_config.data_based_root_dir:
        return file_upload_config.data_based_root_dir
    project_data = Path(__file__).absolute().parent.parent.parent.parent / "data"
    fallback = project_data / "tmp" / "upload"
    fallback.mkdir(parents=True, exist_ok=True)
    logger.warning(f"未配置DATA_BASED_ROOT_DIR，上传文件将保存到：{fallback}")
    return str(fallback)


@app.post("/upload", summary="上传文件接口", description="自动触发教育知识库导入工作流")
async def upload_file(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(..., description="需要上传的文件（md、docx、pdf）"),
        content_type: Optional[str] = Form(None, description="内容类型（可选，不传则自动识别）"),
):
    """
    上传文件接口：
      1. 保存文件到本地（DATA_BASED_ROOT_DIR/YYYYMMDD/task_id/）
      2. 同步上传到 MinIO（可选，失败不阻断主流程）
      3. 后台启动 LangGraph 导入工作流
    """
    # 1. 构建本地文件存储目录
    data_based_root_dir = _resolve_upload_root()
    data_dir = os.path.join(data_based_root_dir, datetime.now().strftime("%Y%m%d"))

    # 2. 生成唯一任务标识
    task_id = str(uuid.uuid4())

    # 3. 任务追踪：上传中
    add_running_task(task_id, "upload_file")

    # 4. 构建本地任务目录并保存文件
    local_dir = os.path.join(data_dir, task_id)
    os.makedirs(local_dir, exist_ok=True)
    local_file_path = os.path.join(local_dir, file.filename)
    with open(local_file_path, "wb") as file_buffer:
        shutil.copyfileobj(file.file, file_buffer, length=1024 * 1024)

    # 5. 上传到 MinIO（失败仅记录日志）
    try:
        minio_client = get_minio_client()
        minio_object_name = f"edu_files/{datetime.now().strftime('%Y%m%d')}/{file.filename}"
        minio_client.fput_object(minio_config.bucket_name, minio_object_name, local_file_path)
    except Exception as e:
        logger.warning(f"文件上传到MinIO失败: {e}")

    # 6. 内容类型（自动识别 or 手动指定）
    file_title = Path(file.filename).stem
    detected_type = detect_content_type(file_title, local_file_path)
    final_type = content_type or detected_type
    logger.info(f"内容类型：{final_type}（自动识别：{detected_type}，前端指定：{content_type or '无'}）")

    # 7. 任务追踪：上传完成
    add_done_task(task_id, "upload_file")

    # 8. 启动后台导入工作流
    background_tasks.add_task(run_graph_task, task_id, local_dir, local_file_path)

    return {
        "code": 200,
        "message": "文件上传成功",
        "task_id": task_id,
        "content_type": final_type,
        "content_type_cn": CONTENT_TYPE_CN.get(final_type, final_type),
    }


@app.get("/status/{task_id}", summary="任务状态查询接口", description="前端根据task_id轮询")
async def get_task_progress(task_id: str):
    task_status_info: Dict = get_task_info(task_id)
    return task_status_info


@app.get("/health")
async def health():
    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
