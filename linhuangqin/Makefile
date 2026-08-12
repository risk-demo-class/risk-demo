# ─────────────────────────────────────────────
# Logistics Risk - Makefile
# 常用命令速查
# ─────────────────────────────────────────────

.PHONY: help init-db generate-data train reset-db clean lint test all

SHELL := /bin/bash
VENV := .venv
PYTHON := $(VENV)/Scripts/python

help: ## 显示此帮助
	@echo "可用命令:"
	@echo "  make init-db      初始化数据库 (建表)"
	@echo "  make generate     生成业务数据 (200条物流事件)"
	@echo "  make risky        生成高风险用户 (30个)"
	@echo "  make train        训练 XGBoost 模型"
	@echo "  make reset        重置: 删库重建 + 生成数据"
	@echo "  make clean        清理 __pycache__ 和 .pyc"
	@echo "  make lint         代码检查 (ruff)"
	@echo "  make test         运行单元测试"
	@echo "  make all          完整验证流程"

init: ## 初始化环境
	@if [ ! -d "$(VENV)" ]; then \
		python -m venv $(VENV); \
		$(PYTHON) -m pip install --upgrade pip; \
		$(PYTHON) -m pip install -r requirements.txt; \
	fi
	@echo "✓ 环境就绪"

init-db: init ## 初始化数据库
	$(PYTHON) scripts/init_db.py

generate: init-db ## 生成业务数据
	$(PYTHON) scripts/gen_logistics_data.py --count 200
	$(PYTHON) scripts/gen_risky_users.py --count 30

train: generate ## 训练模型
	$(PYTHON) scripts/train_xgb_model.py

reset: clean init-db ## 完全重置: 删库重建
	$(PYTHON) scripts/gen_logistics_data.py --count 200
	$(PYTHON) scripts/gen_risky_users.py --count 30

clean: ## 清理缓存
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	echo "✓ 清理完成"

lint: init ## 代码检查
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

test: init ## 运行测试
	$(PYTHON) -m pytest tests/ -v --tb=short

all: lint test generate train ## 完整验证
	@echo ""
	@echo "========================================"
	@echo "✓ 全部通过!"
	@echo "  数据库: 21 张表"
	@echo "  业务数据: >= 100 条物流事件"
	@echo "  高风险用户: >= 30 个"
	@echo "  模型: xgb_model.json 已生成"
	@echo "========================================"

# 开发调试命令
dev: init-db generate ## 开发调试 (建库 + 数据)
	@echo "启动服务: python scripts/main.py"

serve: ## 启动服务 (需先 init-db)
	$(PYTHON) scripts/main.py
