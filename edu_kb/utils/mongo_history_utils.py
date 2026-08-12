# -*- coding: utf-8 -*-
import json
from datetime import datetime
from typing import List, Dict, Any

from bson import ObjectId
from pymongo import MongoClient, DESCENDING

from edu_kb.config.config import mongo_config
from edu_kb.tool.logger import logger


class HistoryMongoTool:
    def __init__(self):
        try:
            self.mongo_url = mongo_config.mongo_url
            self.db_name = mongo_config.mongo_db_name
            self.client = MongoClient(self.mongo_url)
            self.db = self.client[self.db_name]
            self.chat_message = self.db["chat_message"]
            # 会话 + 时间倒序索引
            self.chat_message.create_index([("session_id", 1), ("ts", -1)])
            logger.info("MongoDB连接成功")
        except Exception as e:
            logger.exception(f"MongoDB连接失败: {e}")
            raise


# 延迟加载
_history_mongo_tool = None


def get_history_mongo_tool() -> HistoryMongoTool:
    global _history_mongo_tool
    if _history_mongo_tool is None:
        _history_mongo_tool = HistoryMongoTool()
    return _history_mongo_tool


def clear_history(session_id: str) -> int:
    """清空会话历史记录"""
    try:
        mongo_tool = get_history_mongo_tool()
        result = mongo_tool.chat_message.delete_many({"session_id": session_id})
        return result.deleted_count
    except Exception as e:
        logger.error(f"删除历史记录失败：{session_id}，{e}")
        return 0


def save_chat_message(
        session_id: str,
        role: str,
        text: str,
        rewritten_query: str = "",
        entities: List[str] = None,
        references: List[Dict] = None,
        image_urls: List[str] = None,
        intent: str = "",
        message_id: str = None,
) -> str:
    """新增或更新会话消息"""
    try:
        document = {
            "session_id": session_id,
            "role": role,
            "text": text,
            "rewritten_query": rewritten_query,
            "entities": entities or [],
            "references": references or [],
            "image_urls": image_urls or [],
            "intent": intent,
            "ts": datetime.now().timestamp(),
        }
        mongo_tool = get_history_mongo_tool()
        if message_id:
            mongo_tool.chat_message.update_one(
                {"_id": ObjectId(message_id)},
                {"$set": document},
            )
            return message_id
        result = mongo_tool.chat_message.insert_one(document)
        return str(result.inserted_id)
    except Exception as e:
        raise RuntimeError(f"保存或更新失败：{session_id}，{e}") from e


def update_message_entities(ids: List[str], entities: List[str]) -> int:
    """更新聊天记录中的知识实体字段"""
    try:
        mongo_tool = get_history_mongo_tool()
        object_ids = [ObjectId(id) for id in ids]
        result = mongo_tool.chat_message.update_many(
            {"_id": {"$in": object_ids}},
            {"$set": {"entities": entities}},
        )
        return result.modified_count
    except Exception as e:
        logger.error(f"更新知识实体失败: {e}")
        return 0


def get_recent_messages(session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """获取聊天历史记录（按时间倒序）"""
    try:
        mongo_tool = get_history_mongo_tool()
        cursor = mongo_tool.chat_message.find(
            {"session_id": session_id}
        ).sort("ts", DESCENDING).limit(limit)
        return list(cursor)
    except Exception as e:
        logger.error(f"获取最近历史消息失败: {e}")
        return []


# 定义自定义 JSON Encoder，解决原生 json 工具无法序列化 ObjectId 的问题
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def format_json(data: Any, indent: int = 4, ensure_ascii: bool = False) -> str:
    return json.dumps(data, indent=indent, ensure_ascii=ensure_ascii, cls=MongoJSONEncoder)
