# 制造业风控系统 (Manufacturing_Risk)

仿 **AI_Risk 电商风控** 架构的制造业风控项目: 经销商订货 / 设备保修 / 采购订单 / 售后维修 四大业务边界。

## 快速开始 (3 步)

```bash
cd "/Users/cuixiaojing/Documents/Project_pycharm/02_电商风控【new】/Manufacturing_risk"

# 1. 安装依赖 (uv)
uv sync                      # 或: uv venv && uv pip install -e .

# 2. 初始化数据库 (建库建表 + 8 条规则) + 生成业务演示数据
uv run python scripts/init_db.py --yes
uv run python scripts/gen_data.py

# 3. 启动服务
uv run python run_app.py     # 浏览器打开 http://127.0.0.1:8000
```

> MySQL 连接配置在 `.env` (默认 localhost:3306 / root / Aa666666 / manufacturing_risk), 按需修改。

## 项目结构 (分层)

```
API(routers) → Service → Engine(feature/rule/decision) → ORM(models*) → MySQL
```

| 层 | 文件 | 职责 |
|---|---|---|
| 页面/API | app/routers/*.py | 6 个页面 + 8 组 REST API |
| 业务流 | app/service/event.py | process_event 4 步: 校验→补参→黑名单拦截→7步流水线 |
| 校验 | app/service/validator.py | 实体存在性 / 事件-来源匹配 / 归属防越权 |
| 特征 | app/engine/feature.py | 26 维特征 (经销商12 + 订单6 + 产品3 + 保修5) |
| 规则 | app/engine/rule.py | JSON 条件表达式求值 (14 种 op + and/or 嵌套) |
| 决策 | app/engine/decision.py | 7 步流水线 + 一票否决 + 双轨融合 |
| ML | app/engine/ml_model.py | XGBoost 双轨融合 (默认关闭=纯规则) |
| ORM | app/models_business.py (7) / models_risk.py (8) | 15 张表映射 |
| 建表 | sql/*.sql (权威) + scripts/init_db.py | 7 业务表 + 8 风控表 + 8 规则 |

## 表清单 (15 张 = 7 业务 + 8 风控)

**业务表 (7)**: user_info / product / dealer_info / order_info / warranty_record / cross_region_report / blacklist_extra
**风控表 (8)**: risk_rule / risk_event / risk_feature / risk_assessment / risk_case / risk_blacklist / risk_user_profile / risk_action_log

## 业务规则 (8 条, 说明书 D.2)

| 编号 | 规则 | 事件 | 等级/决策 | 核心特征 |
|---|---|---|---|---|
| R001 | 跨区串货举报 | 串货举报 | 极高/拒绝 | order_cross_region_report_count ≥ 2 |
| R002 | 保修期外高频保修 | 保修申请 | 高/人工审核 | warranty_is_expired=1 AND warranty_apply_count_30d ≥ 2 |
| R005 | 大额经销商囤货 | 经销商订货 | 高/人工审核 | order_total_amount > 100万 |
| R008 | 套保嫌疑 | 售后维修 | 极高/拒绝 | sn_repair_count_90d ≥ 2 |
| R012 | 新经销商大单 | 经销商订货 | 中/标记 | 签约<30天 + 首单 + >50万 |
| R018 | 维修费用异常 | 售后维修 | 中/标记 | repair_cost_msrp_ratio > 0.6 |
| R025 | 经销商资质过期 | 经销商订货 | 中/标记 | dealer_contract_expired = 1 |
| R030 | 黑经销商拦截 | 通用 | 极高/拒绝 | dealer_blacklist_hit = 1 |

## 评分与决策 (跟电商版一致)

- 阈值: PASS=30 / MARK=60 / REVIEW=80
- 评分: `final_score = max(各规则分) + 3×(命中数-1)`, 上限 100
- 一票否决: 任意"极高"规则命中 → 强制拒绝 + 抬分到 90 (融合前+融合后双保险)
- 双轨融合: `final = 0.5×rule + 0.5×ml` (XGB_ENABLED=false 时纯规则)
- 黑名单前置拦截: 经销商ID/设备SN/维修工/用户 4 类, 撞黑直接拒 (不建案); 业务黑名单走 R030 规则建案

## 演示场景 (gen_data.py 造数后直接可用)

| 场景 | 事件类型 | source_id | user_id | 预期 |
|---|---|---|---|---|
| 串货举报 | 串货举报 | REP002 | U005 | R001 拒绝 |
| 保修期外高频 | 保修申请 | WAR012 | D008 | R002 人工审核 |
| 大额囤货 | 经销商订货 | ORD003 | D002 | R005+R025 审核/标记 |
| 套保嫌疑 | 售后维修 | WAR004 | D001 | R008 拒绝 |
| 新经销商大单 | 经销商订货 | ORD005 | D004 | R012 标记 |
| 维修费用异常 | 售后维修 | WAR020 | D008 | R018 标记 |
| 黑经销商 | 经销商订货 | ORD010 | D007 | R030 拒绝 |
| 黑名单拦截 | 经销商订货 | ORD004 | D003 | 前置拦截拒绝 |
| 正常通过 | 售后维修 | WAR022 | D002 | 通过 |

## AI 助手 (双层架构)

- **LLM 模式**: 复用电商 .env 的 DeepSeek key (`api.deepseek.com / deepseek-v4-flash`), LangChain DeepAgent + 8 个制造业工具, 自动查库回答
- **内置规则模式**: 没配 key 或没装 langchain 时自动降级 — 关键词意图识别 + 直接查库 (零依赖)
- 页面: 侧边栏「AI 助手」/ 或访问 http://127.0.0.1:8000/chat

试这些问法: `查看今天的风控统计` / `查待审核的案件` / `分析 D002 的风险画像` / `对 ORD003 做经销商订货风险检查 user=D002` / `分析规则命中效果` / `查黑名单`

## 常见问题

- **跑法**: 所有 demo 脚本用 `uv run python -m app.xxx` (项目根目录), 直接 `python app/xxx.py` 会报 `No module named 'app'` (sys.path 问题, 跟电商版同坑)
- **建表**: sql/*.sql 是权威, 改字段要"ORM 类 + DDL 双写"
- **ML 双轨**: 默认 XGB_ENABLED=false 纯规则; 想开 ML: `uv sync --extra ml` → 训练脚本 `scripts/train_xgb_model.py` → `.env` 设 XGB_ENABLED=true
