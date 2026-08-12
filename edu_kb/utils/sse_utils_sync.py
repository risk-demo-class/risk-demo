# -*- coding: utf-8 -*-
import asyncio
import json
import logging
import queue
from typing import Dict, Any, AsyncGenerator
from fastapi import Request

from edu_kb.utils.task_utils import (
    get_task_status,
    get_done_task_list,
    get_running_task_list,
)


class SSEEvent:
    PROGRESS = "progress"  # 任务节点进度
    DELTA = "delta"        # LLM 流式输出增量
    FINAL = "final"        # 最终完整答案
    ERROR = "error"        # 错误信息


# 全局 SSE 任务队列存储（Key: task_id, Value: queue.Queue）
sse_queues: Dict[str, queue.Queue] = {}


def create_sse_queue(task_id: str):
    """创建并注册一个 sse 队列"""
    sse_queues[task_id] = queue.Queue()


def remove_sse_queue(task_id: str):
    """移除 sse 队列"""
    sse_queues.pop(task_id, None)


def push_sse_event(task_id: str, event: str, data: Dict[str, Any]):
    """通过 task_id 推送事件到 SSE 队列"""
    stream_queue = sse_queues.get(task_id)
    if stream_queue:
        stream_queue.put({"event": event, "data": data})


async def event_generator(task_id: str, request: Request) -> AsyncGenerator:
    """流式输出结果的消费者：队列数据 -> SSE 协议数据包"""

    # 1. 校验：等待队列创建
    while task_id not in sse_queues:
        await asyncio.sleep(1)

    sse_queue = sse_queues.get(task_id)
    loop = asyncio.get_event_loop()

    try:
        while True:
            # 2. 判断前端 sse 连接是否关闭
            if await request.is_disconnected():
                return
            try:
                msg = await loop.run_in_executor(None, sse_queue.get, True, 1)
                event_type = msg.get("event")
                event_data = msg.get("data")
                payload = json.dumps(event_data, ensure_ascii=False)
                yield f"event: {event_type}\ndata: {payload}\n\n"
            except queue.Empty:
                logging.info("队列为空...请稍等")
                await asyncio.sleep(1)
                continue
    except (ConnectionResetError, BrokenPipeError):
        # 客户端中断（关闭了窗口或者浏览器）
        return
    except asyncio.CancelledError:
        raise
    finally:
        remove_sse_queue(task_id)


def push_progress(task_id: str):
    """推送一次任务进度事件"""
    push_sse_event(task_id, SSEEvent.PROGRESS, {
        "status": get_task_status(task_id),
        "done_list": get_done_task_list(task_id),
        "running_list": get_running_task_list(task_id),
    })
