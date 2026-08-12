# 银行风控 Agent 设计

## 定位

Agent 是风控分析师的只读分析与受控操作入口，不替代规则引擎。风险检查最终仍由 `process_event()` 和 `run_risk_check()` 完成，LLM 不能自行伪造评分。

## 八个工具

| 工具 | 职责 | 关键参数 |
|---|---|---|
| `risk_check` | 执行四场景实时检查 | user_id、event_type、source_id |
| `query_cases` | 查询案件和状态统计 | status、page |
| `query_user_profile` | 查询/实时计算客户画像 | user_id |
| `manage_blacklist` | 添加、检查、列出、软删除名单 | action、type、value |
| `query_dashboard_stats` | 今日指标、7 天趋势、TOP5 规则 | 无 |
| `analyze_risk_trend` | 指定时间窗风险分布 | days |
| `analyze_rule_effectiveness` | 规则命中次数/命中率 | 无 |
| `query_business_data` | 查交易、贷款、登录、卡和共用设备 | query_type |

## 调用原则

1. 先识别意图，再选择最小工具集合。
2. `risk_check` 只接受四类事件；业务 ID 必须来自对应表。
3. 黑名单变更经过 service，写审计日志并使用软删除。
4. 工具返回可追踪错误 ID，不向用户暴露数据库连接信息。
5. 业务查询不会返回卡号/身份证号哈希，更不会返回敏感明文。
6. 没有配置 `LLM_API_KEY` 时，核心 API 与页面仍可独立运行。

## 示例编排

“为什么 U002 的 TXN_GEO_001 被拒绝？”应先调用 `risk_check` 得到命中规则，再调用 `query_user_profile` 补充常住地、历史行为解释；不需要调用黑名单写操作。

“把设备 DEV-X 加黑”属于外部状态变更，调用 `manage_blacklist(action=add, blacklist_type=设备指纹, ...)`，结果会同步写入审计日志。
