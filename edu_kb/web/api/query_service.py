# -*- coding: utf-8 -*-
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse, StreamingResponse, RedirectResponse

from edu_kb.query_process.main_graph import KBQueryWorkflow
from edu_kb.tool.logger import logger
from edu_kb.utils.mongo_history_utils import get_recent_messages, clear_history
from edu_kb.utils.sse_utils_sync import (
    event_generator,
    create_sse_queue,
    push_progress,
)
from edu_kb.utils.task_utils import (
    update_task_status,
    TASK_STATUS_PROCESSING,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
)

app = FastAPI(
    title="教育知识库：查询 API",
    description="课程介绍 / 文档检索 / 题目检索 / 知识问答（支持多轮、流式输出）",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/chat.html")
async def chat():
    html_path = Path(__file__).absolute().parent.parent / "page" / "chat.html"
    return FileResponse(html_path)


@app.get("/import.html")
async def redirect_import_page():
    """导入页由导入服务(8000)提供，这里做兼容跳转"""
    return RedirectResponse(url="http://127.0.0.1:8000/import.html")


class QueryRequest(BaseModel):
    """查询请求数据结构"""
    query: str = Field(..., description="查询内容")
    session_id: str = Field(None, description="会话ID")


def run_query_graph(session_id: str, task_id: str, user_query: str):
    """后台任务：执行查询工作流"""
    try:
        update_task_status(task_id, TASK_STATUS_PROCESSING)
        push_progress(task_id)

        init_state = {
            "original_query": user_query,
            "session_id": session_id,
            "task_id": task_id,
        }
        for chunk in KBQueryWorkflow.create_and_run(init_state, stream=True):
            for node_name, node_result in chunk.items():
                logger.info(f"{node_name}: {node_result}")

        update_task_status(task_id, TASK_STATUS_COMPLETED)
        push_progress(task_id)
    except Exception as e:
        update_task_status(task_id, TASK_STATUS_FAILED)
        push_progress(task_id)
        logger.error(f"流程执行异常: {e}")


@app.post("/query")
async def query(background_tasks: BackgroundTasks, request: QueryRequest):
    user_query = request.query
    session_id = request.session_id or str(uuid.uuid4())
    task_id = str(uuid.uuid4())

    create_sse_queue(task_id)
    background_tasks.add_task(run_query_graph, session_id, task_id, user_query)

    return {
        "message": "查询请求已经提交，结果正在处理中...",
        "session_id": session_id,
        "task_id": task_id,
    }


@app.get("/stream/{task_id}")
async def stream(task_id: str, request: Request):
    return StreamingResponse(
        event_generator(task_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.delete("/history/{session_id}")
async def clear_chat_history(session_id: str):
    count = clear_history(session_id)
    return {"message": "历史会话已清空", "deleted_count": count}


@app.get("/history/{session_id}")
async def history(session_id: str, limit: int = 50):
    try:
        records = reversed(get_recent_messages(session_id, limit=limit))
        items = [{
            "_id": str(r.get("_id")) if r.get("_id") is not None else "",
            "session_id": r.get("session_id", ""),
            "role": r.get("role", ""),
            "text": r.get("text", ""),
            "rewritten_query": r.get("rewritten_query", ""),
            "entities": r.get("entities", []),
            "references": r.get("references", []),
            "image_urls": r.get("image_urls", []),
            "intent": r.get("intent", ""),
            "ts": r.get("ts"),
        } for r in records]
        return {"session_id": session_id, "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"history error: {e}") from e


@app.get("/health")
async def health():
    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)
