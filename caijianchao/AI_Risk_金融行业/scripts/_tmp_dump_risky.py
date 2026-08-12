# -*- coding: utf-8 -*-
"""临时: gen_risky_users.py 全文 (带行号)"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
with open("scripts/gen_risky_users.py", encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        print(f"{i:4d}| {line.rstrip()}")
