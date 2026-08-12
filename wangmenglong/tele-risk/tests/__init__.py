"""
电信风控测试套件 (精简版, 5 个文件覆盖核心)
============================================
相比 ai_risk 的 37 个测试, tele-risk 只测核心逻辑 (无需 DB 的纯计算测试):

  test_rule_engine.py     规则引擎 (JSON 条件求值 + 12 条预置规则语法)
  test_decision.py        决策引擎 (评分公式 + 一票否决 + 双轨融合)
  test_feature_columns.py 特征列对齐 (feature.py ↔ ml_model ↔ train 脚本)
  test_schemas.py         Pydantic schema 构造 + 序列化
  test_api_smoke.py       API 路由注册 + 健康检查 (不打真实 DB)
"""
