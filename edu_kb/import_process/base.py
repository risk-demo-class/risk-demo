# -*- coding: utf-8 -*-
import time
from abc import ABC, abstractmethod

from edu_kb.import_process.state import ImportGraphState
from edu_kb.tool.logger import logger
from edu_kb.utils.task_utils import (
    add_running_task,
    add_done_task,
    add_node_duration,
)


class NodeBase(ABC):
    """导入流程节点基类：统一负责任务追踪、耗时统计与异常上抛"""

    name: str = "node_base"

    def __init__(self):
        if self.name == "node_base":
            raise ValueError(f"{self.__class__.__name__} 必须设置 name 属性")

    def __call__(self, state: ImportGraphState):
        try:
            task_id = state.get("task_id", "")

            # 1. 记录节点开始
            add_running_task(task_id, self.name)
            start_time = time.time()

            # 2. 执行节点
            result = self.process(state)

            # 3. 记录节点结束与耗时
            end_time = time.time()
            add_done_task(task_id, self.name)
            add_node_duration(task_id, self.name, end_time - start_time)

            return result
        except Exception as e:
            logger.error(f"{self.name} 执行失败：{e}")
            raise

    @abstractmethod
    def process(self, state: ImportGraphState):
        """节点的核心处理逻辑"""
        pass
