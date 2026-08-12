"""训练数据纯净性单测: 标签映射 + 特征矩阵构造"""
import numpy as np

from scripts.train_xgb_model import _decision_to_label


def test_decision_to_label():
    assert _decision_to_label("通过") == 0
    assert _decision_to_label("标记") == 0
    assert _decision_to_label("人工审核") == 1
    assert _decision_to_label("拒绝") == 1


def test_label_balance_logic():
    """正例 = 人工审核/拒绝, 负例 = 通过/标记."""
    labels = [_decision_to_label(d) for d in ["通过", "标记", "人工审核", "拒绝"]]
    assert labels == [0, 0, 1, 1]


def test_feature_matrix_shape_from_columns():
    from app.engine.ml_model import FEATURE_COLUMNS
    feats = {col: 0.0 for col in FEATURE_COLUMNS}
    X = np.array([[feats[c] for c in FEATURE_COLUMNS]])
    assert X.shape == (1, 28)
