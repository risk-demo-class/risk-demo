"""兼容旧导入路径；新代码统一使用 app.config。"""
from app.config import BLACKLIST_TYPES, BusinessEventType, Settings, settings

__all__ = ["BLACKLIST_TYPES", "BusinessEventType", "Settings", "settings"]
