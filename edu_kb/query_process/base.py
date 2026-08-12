# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod

from edu_kb.query_process.state import QueryGraphState
from edu_kb.tool.logger import logger
from edu_kb.utils.sse_utils_sync import push_progress
from edu_kb.utils.task_utils import add_running_task, add_done_task


class NodeBase(ABC):
    """查询流程节点基类：统一负责任务追踪与 SSE 进度推送"""

    name: str = "node_base"

    def __init__(self):
        if self.name == "node_base":
            raise ValueError(f"{self.__class__.__name__} 必须设置 name 属性")

    def __call__(self, state: QueryGraphState):
        try:
            task_id = state.get("task_id", "")

            # 1. 记录节点开始 + 推送进度
            add_running_task(task_id, self.name)
            push_progress(task_id)

            # 2. 执行节点
            result = self.process(state)

            # 3. 记录节点结束 + 推送进度
            add_done_task(task_id, self.name)
            push_progress(task_id)
            logger.info(f"{self.name} 结束执行...")
            return result
        except Exception as e:
            logger.error(f"{self.name} 执行失败: {e}")
            raise

    @abstractmethod
    def process(self, state: QueryGraphState):
        """节点的核心处理逻辑"""
        pass
