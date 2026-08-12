# -*- coding: utf-8 -*-
"""临时: gen_risky_users.py 全部 INSERT 语句"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
with open("scripts/gen_risky_users.py", encoding="utf-8") as f:
    lines = f.readlines()
print(f"总行数: {len(lines)}")
for i, line in enumerate(lines, 1):
    if "INSERT" in line or "UPDATE" in line:
        print(f"{i:4d}| {line.rstrip()}")
print("\n=== loan_info 相关完整段 (100-130 行) ===")
for i in range(99, min(135, len(lines))):
    print(f"{i+1:4d}| {lines[i].rstrip()}")
