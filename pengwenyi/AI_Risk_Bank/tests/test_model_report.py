"""
【银行版】测试 - 模型报告 (xgb_metrics.json 生成 + /model 页读取)

验证:
  1. 训练后必须生成 app/engine/xgb_metrics.json
  2. _load_model_metrics 能正确读取并含全部关键指标
  3. 验收: val_auc >= 0.8, best_iteration >= 30, 假收敛检查通过
  4. 特征重要性 TOP10 全部落在 48 维 FEATURE_COLUMNS 中
  5. 文件缺失 / JSON 损坏 → 返回空 dict (页面优雅降级)
"""
import json
from pathlib import Path

from app.engine.ml_model import FEATURE_COLUMNS
from app.routers.pages import _load_model_metrics

ROOT = Path(__file__).resolve().parent.parent
METRICS_PATH = ROOT / "app" / "engine" / "xgb_metrics.json"


class TestMetricsFileGenerated:
    """训练脚本必须输出 xgb_metrics.json (供 /model 页 + README 使用)."""

    def test_metrics_file_exists(self):
        assert METRICS_PATH.exists(), "训练后必须生成 app/engine/xgb_metrics.json"
        assert METRICS_PATH.stat().st_size > 0, "metrics JSON 不能为空"

    def test_file_is_valid_json(self):
        with open(METRICS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict)


class TestMetricsContent:
    """metrics JSON 内容完整, 关键指标达标."""

    def test_all_key_fields_present(self):
        metrics = _load_model_metrics()
        for key in [
            "model", "trained_at", "n_train", "n_pos", "pos_ratio",
            "best_iteration", "auc", "f1", "val_auc", "val_f1",
            "best_f1_threshold", "scale_pos_weight",
            "feature_importance_top10", "fake_convergence_check", "model_path",
        ]:
            assert key in metrics, f"metrics 缺少关键字段: {key}"

    def test_val_auc_meets_acceptance(self):
        """验收标准: val_auc >= 0.8."""
        metrics = _load_model_metrics()
        assert metrics["val_auc"] >= 0.8, (
            f"val_auc={metrics['val_auc']} 不达标 (验收要求 >= 0.8)"
        )

    def test_best_iteration_not_fake(self):
        """best_iteration >= 30 (过小说明假收敛/过拟合)."""
        metrics = _load_model_metrics()
        assert metrics["best_iteration"] >= 30, (
            f"best_iteration={metrics['best_iteration']} < 30, 疑似假收敛"
        )

    def test_fake_convergence_check_ok(self):
        """假收敛检查: ok=True, 无 issues."""
        fc = _load_model_metrics()["fake_convergence_check"]
        assert fc["ok"] is True, f"假收敛检查失败: {fc['issues']}"
        assert fc["issues"] == []
        assert fc["min_best_iter"] >= 30
        assert fc["min_val_auc"] >= 0.7

    def test_train_sample_size_sufficient(self):
        """训练样本量充足 (>= 2000, 银行造数 ~3000)."""
        metrics = _load_model_metrics()
        assert metrics["n_train"] >= 2000, f"n_train={metrics['n_train']} 样本不足"

    def test_feature_importance_top10(self):
        """特征重要性 TOP10: 10 条, 特征全部在 48 维 FEATURE_COLUMNS 中."""
        top10 = _load_model_metrics()["feature_importance_top10"]
        assert len(top10) == 10, f"TOP10 应有 10 条, 实际 {len(top10)}"
        feature_set = set(FEATURE_COLUMNS)
        for item in top10:
            assert item["rank"] == top10.index(item) + 1
            assert item["feature"] in feature_set, (
                f"重要性特征 '{item['feature']}' 不在 48 维特征中"
            )
            assert item["gain"] > 0

    def test_model_uses_bank_name(self):
        metrics = _load_model_metrics()
        assert "银行" in metrics["model"], "模型名称应为银行版"


class TestLoadModelMetricsFallback:
    """_load_model_metrics 优雅降级 (页面不崩)."""

    def test_missing_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.routers.pages._BASE_DIR", str(tmp_path))
        assert _load_model_metrics() == {}

    def test_invalid_json_returns_empty(self, tmp_path, monkeypatch):
        metrics_dir = tmp_path / "app" / "engine"
        metrics_dir.mkdir(parents=True)
        (metrics_dir / "xgb_metrics.json").write_text("{bad json", encoding="utf-8")
        monkeypatch.setattr("app.routers.pages._BASE_DIR", str(tmp_path))
        assert _load_model_metrics() == {}


class TestModelReportPage:
    """模型报告页模板存在且绑定 metrics 展示."""

    def test_template_exists(self):
        tpl = ROOT / "templates" / "model_report.html"
        assert tpl.exists(), "缺少 model_report.html 模板"

    def test_template_renders_metrics(self):
        html = (ROOT / "templates" / "model_report.html").read_text(encoding="utf-8")
        assert "val_auc" in html, "模板应展示 val_auc"
        assert "feature_importance" in html, "模板应展示特征重要性"
        assert "fake_convergence" in html, "模板应展示假收敛检查"
