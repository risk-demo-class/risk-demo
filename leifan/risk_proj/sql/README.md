# Python 数据库建表程序

本目录只保存可直接运行的 Python 建表程序。程序读取项目根目录 `.env` 中的
`MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD` 和
`MYSQL_DATABASE`，使用当前 SQLAlchemy ORM 定义创建 MySQL 8.0 表结构。

## 一次创建全部表

在项目根目录执行：

```powershell
uv run python sql/init_all.py
```

数据库不存在时会自动创建，已有表不会重复创建，也不会清空已有数据。

## 按类别创建

```powershell
# 用户、乘机人、支付账户、订单、订单乘客
uv run python sql/create_business_core.py

# 签证、酒店、机票、跟团游预订，以及所依赖的基础业务表
uv run python sql/create_booking_products.py

# 黑名单、规则、评分、命中、审核案件、审计日志，以及所依赖的基础业务表
uv run python sql/create_risk_control.py

# 员工、角色、权限及关联表
uv run python sql/create_auth_rbac.py
```

需要创建到其他数据库时可以临时指定数据库名：

```powershell
uv run python sql/init_all.py --database risk_proj_test
```

这些程序用于初始化缺失的表，不负责修改已存在表的字段。已有数据库的字段变更仍应使用迁移脚本。
