#!/usr/bin/env bash
set -Eeuo pipefail

# 官方 MySQL entrypoint 会 source 本脚本并提供 docker_process_sql。
# 保持核心 DDL 文件不变，只在导入流中去掉其历史库名切换语句。
sed '/^[[:space:]]*USE[[:space:]]\+ecs[[:space:]]*;[[:space:]]*$/Id' \
  /opt/logistics-init/init_risk_tables.sql \
  | docker_process_sql --database="$MYSQL_DATABASE"

docker_process_sql --database="$MYSQL_DATABASE" \
  < /opt/logistics-init/init_risk_data.sql
