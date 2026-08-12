# EduGuard 项目设计图

本文档根据当前项目代码绘制，覆盖系统架构、风险数据流、XGBoost 训练流程，以及“登录—风险检查—案件分配—人工审核”的核心交互时序。

## 1. 项目架构图

```mermaid
flowchart TB
    subgraph USER["访问角色"]
        ADMIN["风控管理员"]
        REVIEWER["审核员"]
    end

    subgraph PRESENTATION["表现层"]
        BROWSER["浏览器"]
        VIEW["Jinja2 模板<br/>HTML / CSS / JavaScript / Chart.js"]
    end

    subgraph APPLICATION["FastAPI 应用层"]
        MIDDLEWARE["AuthenticationMiddleware<br/>会话、角色、页面与 API 权限"]
        ROUTERS["Routers<br/>auth / risk / case / rule / user<br/>dashboard / blacklist / assessment / agent"]
        SCHEMAS["Pydantic Schemas<br/>请求校验与响应序列化"]
    end

    subgraph DOMAIN["业务服务与风控引擎"]
        SERVICES["Services<br/>事件、案件、告警、审计"]
        FEATURES["25 维特征工程"]
        RULES["规则引擎<br/>条件匹配与规则评分"]
        XGB["XGBoost 推理<br/>高风险概率"]
        DECISION["融合决策<br/>评分、等级、动作、一票否决"]
        AGENT["智能助手<br/>Agent / LLM"]
    end

    subgraph INFRA["数据与基础设施层"]
        ORM["SQLAlchemy<br/>AsyncSession"]
        MYSQL[("MySQL 8<br/>业务、风控与系统数据")]
        MODEL[("xgb_model.json")]
        SCHEDULER["后台调度器<br/>案件超时关闭 / 告警检查"]
    end

    ADMIN --> BROWSER
    REVIEWER --> BROWSER
    BROWSER --> MIDDLEWARE
    MIDDLEWARE --> ROUTERS
    ROUTERS <--> SCHEMAS
    ROUTERS --> SERVICES
    ROUTERS --> AGENT
    ROUTERS --> VIEW
    VIEW --> BROWSER

    SERVICES --> FEATURES
    FEATURES --> RULES
    FEATURES --> XGB
    RULES --> DECISION
    XGB --> DECISION
    DECISION --> SERVICES
    AGENT --> SERVICES

    SERVICES --> ORM
    FEATURES --> ORM
    RULES --> ORM
    ORM <--> MYSQL
    MODEL --> XGB
    SCHEDULER --> SERVICES
```

该项目采用分层结构：页面请求先经过认证中间件，再进入路由层；路由调用业务服务与风控引擎；持久化统一通过 SQLAlchemy 异步会话访问 MySQL。XGBoost 无法加载时，系统可降级为纯规则模式。

## 2. 数据流图

```mermaid
flowchart LR
    BUSINESS[("教育业务数据<br/>用户 / 课程 / 订单 / 学习进度<br/>退费 / 学历认证 / 设备绑定")]
    REQUEST["风险检查请求<br/>user_id + event_type + source_id"]
    VALIDATE["校验业务实体<br/>解析事件上下文"]
    BLACKLIST[("risk_blacklist<br/>用户 / 学号 / 身份证 / 设备")]
    HIT{"命中黑名单？"}
    DIRECT["直接拒绝<br/>风险分 100"]

    EVENT[("risk_event")]
    FEATURE["计算 25 维特征"]
    SNAPSHOT[("risk_feature<br/>特征快照")]
    RULE_TABLE[("risk_rule<br/>启用规则")]
    RULE_ENGINE["规则匹配与评分"]
    MODEL[("XGBoost 模型")]
    ML["模型推理<br/>P（高风险）"]
    FUSION["规则分 + 模型分融合<br/>动作下限 + 一票否决"]
    RESULT{"最终决策"}
    RESPONSE["风险检查响应"]

    ASSESSMENT[("risk_assessment<br/>评分、等级、决策、命中规则")]
    PROFILE[("risk_user_profile<br/>用户风险画像")]
    CASE[("risk_case<br/>待审核 / 审核中 / 终态")]
    SYSUSER[("sys_user<br/>管理员 / 审核员")]
    ADMIN["管理员分配案件"]
    REVIEWER["审核员复核"]
    ACTION[("risk_action_log<br/>审计留痕")]

    BUSINESS --> VALIDATE
    REQUEST --> VALIDATE
    VALIDATE --> HIT
    BLACKLIST --> HIT
    HIT -- "是" --> DIRECT --> RESPONSE
    HIT -- "否" --> EVENT

    BUSINESS --> FEATURE
    EVENT --> FEATURE
    FEATURE --> SNAPSHOT
    FEATURE --> RULE_ENGINE
    RULE_TABLE --> RULE_ENGINE
    FEATURE --> ML
    MODEL --> ML
    RULE_ENGINE --> FUSION
    ML --> FUSION
    FUSION --> RESULT

    RESULT --> ASSESSMENT
    RESULT --> PROFILE
    RESULT -- "通过 / 标记" --> RESPONSE
    RESULT -- "人工审核 / 拒绝" --> CASE
    CASE --> RESPONSE

    SYSUSER --> ADMIN
    ADMIN --> CASE
    ADMIN --> ACTION
    CASE --> REVIEWER
    SYSUSER --> REVIEWER
    REVIEWER --> CASE
    REVIEWER --> ACTION
    REVIEWER -. "拒绝时可选加入" .-> BLACKLIST
```

黑名单位于流水线最前端，命中后直接短路拒绝，不写入普通风险事件和评估样本。未命中时，系统保存事件、特征快照和评估结果；只有“人工审核”或“拒绝”决策会生成案件。

## 3. XGBoost 训练流程图

```mermaid
flowchart TD
    START["开始训练"]
    SOURCE{"选择训练数据来源"}

    SYNTHETIC["教学合成路径<br/>train_education_model.py"]
    SCENARIO["按教育业务场景权重采样<br/>正常报名、退费、认证及风险场景"]
    GEN["生成 25 维特征<br/>加入 2% 标签噪声"]
    CSV[("education_training_data.csv")]

    HISTORY["历史数据路径<br/>train_xgb_model.py"]
    ASSESS[("MySQL risk_assessment<br/>仅选择 ml_score IS NULL")]
    FEATURE_TABLE[("MySQL risk_feature")]
    PIVOT["按 event_id 透视为 25 维宽表"]

    LABEL["构造二分类标签<br/>0 = 通过 / 标记<br/>1 = 人工审核 / 拒绝"]
    QUALITY{"数据质量检查<br/>样本量、25 维完整性、正负例比例"}
    SPLIT["分层拆分训练集 / 验证集<br/>保持正负样本比例"]
    WEIGHT["计算 scale_pos_weight<br/>并设置上限防止过拟合"]
    DMATRIX["转换为 XGBoost DMatrix<br/>固定 FEATURE_NAMES 顺序"]
    WARMUP["Warmup 训练<br/>避免过早停止造成假收敛"]
    TRAIN["继续训练 + Early Stopping<br/>监控 AUC 与 LogLoss"]
    EVAL{"模型质量评估<br/>AUC / F1 / Accuracy<br/>Precision / Recall"}
    RETRY["调整样本比例、特征或参数<br/>重新训练"]
    MODEL_OUT[("app/engine/xgb_model.json")]
    METRICS[("模型指标与特征重要性<br/>education_model_metrics.json / 日志")]
    LOAD["应用启动时加载模型"]
    INFER["在线推理<br/>25 维特征 → 高风险概率"]
    FALLBACK["加载失败或关闭模型<br/>降级为纯规则决策"]

    START --> SOURCE
    SOURCE -- "教学演示" --> SYNTHETIC --> SCENARIO --> GEN
    GEN --> CSV
    GEN --> LABEL

    SOURCE -- "历史重训" --> HISTORY
    HISTORY --> ASSESS
    HISTORY --> FEATURE_TABLE
    ASSESS --> LABEL
    FEATURE_TABLE --> PIVOT --> LABEL

    LABEL --> QUALITY
    QUALITY -- "不合格" --> RETRY --> SOURCE
    QUALITY -- "合格" --> SPLIT --> WEIGHT --> DMATRIX --> WARMUP --> TRAIN --> EVAL
    EVAL -- "不达标" --> RETRY
    EVAL -- "达标" --> MODEL_OUT
    EVAL -- "输出" --> METRICS
    MODEL_OUT --> LOAD
    LOAD -- "成功" --> INFER
    LOAD -- "失败 / XGB_ENABLED=false" --> FALLBACK
```

项目支持两条训练路径：教学演示可使用固定随机种子生成可复现的教育场景样本；积累历史评估后，可从 MySQL 提取没有模型痕迹的数据进行重训，避免用旧模型输出反向污染标签。

## 4. 核心交互时序图

```mermaid
sequenceDiagram
    autonumber
    participant Admin as 风控管理员
    participant Reviewer as 审核员
    participant Browser as 浏览器
    participant Auth as 认证中间件
    participant API as FastAPI 路由与服务
    participant Engine as 风控引擎
    participant XGB as XGBoost
    participant DB as MySQL

    Admin->>Browser: 打开系统
    Browser->>API: GET /
    API-->>Browser: 303 跳转 /login
    Admin->>Browser: 输入账号和密码
    Browser->>API: POST /api/auth/login
    API->>DB: 查询 sys_user
    DB-->>API: 用户、密码哈希、角色、状态
    API-->>Browser: 设置签名 Cookie，返回角色信息

    Browser->>Auth: GET /dashboard
    Auth->>DB: 校验 Cookie 对应用户及角色
    DB-->>Auth: ADMIN 且账号启用
    Auth->>API: 放行管理员页面
    API-->>Browser: 返回仪表盘

    Admin->>Browser: 发起风险检查
    Browser->>Auth: POST /api/risk/check
    Auth->>API: 鉴权通过
    API->>DB: 校验业务实体、解析事件、查询四类黑名单
    DB-->>API: 业务上下文与黑名单结果

    alt 命中黑名单
        API-->>Browser: 直接拒绝，风险分 100
    else 未命中黑名单
        API->>Engine: 执行风险决策流水线
        Engine->>DB: 查询业务数据和启用规则
        DB-->>Engine: 用户、订单、学习、退费、认证、设备与规则
        Engine->>Engine: 计算 25 维特征并匹配规则
        Engine->>XGB: 25 维特征向量
        XGB-->>Engine: 高风险概率与模型决策
        Engine->>Engine: 融合评分、动作下限与一票否决
        Engine->>DB: 事务写入事件、特征、评估、画像及可选案件
        DB-->>Engine: 提交成功
        Engine-->>API: 最终分数、等级、决策、命中规则
        API-->>Browser: 显示风险检查结果
    end

    Admin->>Browser: 选择案件和审核员
    Browser->>Auth: POST /api/cases/{case_id}/assign
    Auth->>API: 校验 ADMIN 权限
    API->>DB: 校验审核员启用状态，更新案件并记录审计日志
    DB-->>API: 案件进入“审核中”
    API-->>Browser: 返回分配结果

    Note over Reviewer,DB: 审核员登录流程与上方一致，角色为 REVIEWER
    Reviewer->>Browser: 打开审核工作台
    Browser->>Auth: GET /api/cases?active_only=true
    Auth->>API: 校验 REVIEWER 权限
    API->>DB: 按 assignee_id 查询本人案件
    DB-->>API: 仅返回分配给当前审核员的数据
    API-->>Browser: 展示待审核案件

    Reviewer->>Browser: 提交通过、拒绝或关闭结论
    Browser->>Auth: POST /api/cases/{case_id}/review
    Auth->>API: 鉴权通过
    API->>DB: 校验案件归属与状态流转
    opt 拒绝且管理员选择加入黑名单
        API->>DB: 同一事务写入 risk_blacklist
    end
    API->>DB: 更新案件终态并写入 risk_action_log
    DB-->>API: 事务提交成功
    API-->>Browser: 返回审核结果
```

时序图同时体现了三层权限控制：认证中间件验证登录状态，路由验证角色权限，案件接口再按 `assignee_id` 验证数据归属。

## 相关代码位置

- 应用入口：`scripts/main.py`
- 登录和权限：`app/routers/auth.py`、`app/auth.py`
- 风险事件入口：`app/service/event.py`
- 特征、规则、模型与决策：`app/engine/feature.py`、`rule.py`、`ml_model.py`、`decision.py`
- 案件分配与审核：`app/routers/case.py`、`app/service/case.py`
- 数据模型：`app/models_business.py`、`app/models_risk.py`、`app/models_system.py`
- 训练脚本：`scripts/train_education_model.py`、`scripts/train_xgb_model.py`
