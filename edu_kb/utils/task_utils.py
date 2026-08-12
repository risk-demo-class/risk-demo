# -*- coding: utf-8 -*-
from collections import defaultdict
from typing import Dict, List

# ---------------------------
# 内存态任务追踪（单进程）
# ---------------------------
_tasks_running_list: Dict[str, List[str]] = defaultdict(list)
_tasks_done_list: Dict[str, List[str]] = defaultdict(list)
_tasks_duration: Dict[str, Dict[str, float]] = defaultdict(dict)
_tasks_status: Dict[str, str] = {}
_tasks_result: Dict[str, Dict[str, str]] = defaultdict(dict)


TASK_STATUS_PROCESSING = "processing"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_FAILED = "failed"

# 节点名 -> 中文名映射（用于前端展示）
# 注意：这里的 key 应与 LangGraph 的 add_node("xxx", ...) 中的节点名一致。
_NODE_NAME_TO_CN: Dict[str, str] = {
    "upload_file": "开始上传文件",
    "node_entry": "检查文件与内容类型",
    "node_doc_to_md": "文档转Markdown",
    "node_md_img": "Markdown图片处理",
    "node_course_intro_import": "课程介绍解析入库",
    "node_question_bank_import": "题库解析入库",
    "node_document_split": "文档切分",
    "node_metadata_recognition": "教育元数据识别",
    "node_bge_embedding": "向量生成",
    "node_import_milvus": "导入向量库",
    "node_import_entity_index": "知识实体索引",

    # --- Query 流程节点 ---
    "node_query_analyze": "问题分析与意图识别",
    "node_search_course": "课程检索",
    "node_search_docs": "文档检索",
    "node_search_docs_hyde": "文档检索(HyDE)",
    "node_search_questions": "题目检索",
    "node_web_search_mcp": "网络搜索",
    "node_multi_search": "多路检索",
    "node_join": "多路检索合并",
    "node_rrf": "倒排融合",
    "node_rerank": "重排序",
    "node_answer_output": "生成答案",
}


def _to_cn(node_name: str) -> str:
    """将节点名转换为中文展示名；若无映射则返回原名。"""
    return _NODE_NAME_TO_CN.get(node_name, node_name)


def add_running_task(task_id: str, node_name: str) -> None:
    """添加“正在运行”的节点任务（去重）"""
    running = _tasks_running_list[task_id]
    if node_name not in running:
        running.append(node_name)


def add_done_task(task_id: str, node_name: str) -> None:
    """添加“已完成”的节点任务（同时从运行列表移除）"""
    if node_name in _tasks_running_list[task_id]:
        _tasks_running_list[task_id].remove(node_name)
    done = _tasks_done_list[task_id]
    if node_name not in done:
        done.append(node_name)


def get_running_task_list(task_id: str) -> List[str]:
    """获取正在运行节点列表（中文展示）"""
    return [_to_cn(n) for n in _tasks_running_list.get(task_id, [])]


def get_done_task_list(task_id: str) -> List[str]:
    """获取已完成节点列表（中文展示）"""
    return [_to_cn(n) for n in _tasks_done_list.get(task_id, [])]


def get_task_status(task_id: str) -> str:
    """获取当前任务状态"""
    return _tasks_status.get(task_id, "")


def update_task_status(task_id: str, status_name: str) -> None:
    """更新任务状态"""
    _tasks_status[task_id] = status_name


def set_task_result(task_id: str, key: str, value: str) -> None:
    """存储任务结果字段（如 answer / error）"""
    _tasks_result[task_id][key] = value


def get_task_result(task_id: str, key: str, default: str = "") -> str:
    """获取任务结果字段"""
    return _tasks_result.get(task_id, {}).get(key, default)


def add_node_duration(task_id: str, node_name: str, duration: float) -> None:
    """记录节点耗时（秒）"""
    cn_name = _to_cn(node_name)
    _tasks_duration[task_id][cn_name] = round(duration, 2)


def get_node_durations(task_id: str) -> Dict[str, float]:
    """获取所有节点的耗时"""
    return dict(_tasks_duration.get(task_id, {}))


def get_task_info(task_id: str) -> Dict:
    """获取任务的全局信息（状态 + 运行中节点 + 已完成节点 + 耗时）"""
    return {
        "status": get_task_status(task_id),
        "running_list": get_running_task_list(task_id),
        "done_list": get_done_task_list(task_id),
        "durations": get_node_durations(task_id),
    }
