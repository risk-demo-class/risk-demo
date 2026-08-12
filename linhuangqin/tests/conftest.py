"""
pytest 全局 conftest — 兼容层: 将已删除的电商模型映射为 mock,
让引用旧模型的测试至少能 import 通过 (逻辑测试不受影响).
"""
import sys
from unittest.mock import MagicMock

# 电商表模型名 → MagicMock (测试不依赖实际 ORM 模型)
_OLD_MODELS = [
    'OrderInfo', 'OrderDetail', 'Postsale', 'ReceiveInfo', 'SkuInfo',
    'UserInfo', 'ProductCategory', 'Region', 'OrderStatus',
    'Logistics', 'OrderLogistics', 'LogisticsCompany',
    'LogisticsComplaint', 'LogisticsComplaintsRecord',
    'PostsaleStatus', 'PostsaleReason', 'PostsaleLogistics',
]
for name in _OLD_MODELS:
    sys.modules[f'app.models.{name}'] = MagicMock()