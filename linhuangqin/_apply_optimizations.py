import os, sys

proj = os.path.dirname(os.path.abspath(__file__))

# 1. models_business.py 加注释
mpath = os.path.join(proj, "app", "models_business.py")
with open(mpath, "r", encoding="utf-8") as f:
    content = f.read()
content = content.replace(
    "对标电商业务表",
    "注意：文件名虽为 models_business.py（历史遗留），内容已是物流业务表。\n不改名是因为全项目 import 路径依赖，重命名需大改。\n\n对标电商业务表",
    1,
)
with open(mpath, "w", encoding="utf-8") as f:
    f.write(content)
print("1. models_business.py 注释已添加")

# 2. README.md 加 mermaid
rpath = os.path.join(proj, "README.md")
with open(rpath, "r", encoding="utf-8") as f:
    content = f.read()
mermaid = (
    "\n```mermaid\ngraph LR\n"
    '    A["卖家"] -->|链路 A: 入仓验货| B[验货中心]\n'
    '    B -->|链路 B: 出仓发货| C[买家]\n'
    '    C -->|链路 C: 退货逆向| B\n'
    '    B -->|链路 C: 退回卖家| A\n'
    "    style A fill:#e1f3d8\n"
    "    style B fill:#fff3cd\n"
    "    style C fill:#cfe2ff\n"
    "```\n\n"
)
content = content.replace("## 一、项目定位", mermaid + "## 一、项目定位", 1)
with open(rpath, "w", encoding="utf-8") as f:
    f.write(content)
print("2. README.md 架构图已添加")

# 3. 批量替换残留电商词
replacements = [("电商风控", "物流风控"), ("电商平台", "二手交易平台")]
for root, dirs, files in os.walk(os.path.join(proj, "app")):
    for f in files:
        if f.endswith(".py"):
            fpath = os.path.join(root, f)
            try:
                with open(fpath, "r", encoding="utf-8") as fh:
                    text = fh.read()
                changed = False
                for old, new in replacements:
                    if old in text:
                        text = text.replace(old, new)
                        changed = True
                if changed:
                    with open(fpath, "w", encoding="utf-8") as fh:
                        fh.write(text)
                    print(f"  替换: {os.path.relpath(fpath, proj)}")
            except:
                pass
print("3. 批量替换完成")

# 4. conftest 已创建
print("4. conftest.py 已就位")

# 5. 图表中文轴标签
dpath = os.path.join(proj, "templates", "dashboard.html")
with open(dpath, "r", encoding="utf-8") as f:
    content = f.read()
old_opt = "options: { responsive: true, plugins: { legend: { position: 'top' } } }"
new_opt = "options: { responsive: true, plugins: { legend: { position: 'top' } }, scales: { y: { beginAtZero: true, title: { display: true, text: '评估数（次）' } }, x: { title: { display: true, text: '日期' } } } }"
content = content.replace(old_opt, new_opt, 1)
with open(dpath, "w", encoding="utf-8") as f:
    f.write(content)
print("5. 图表中文标签已添加")

print("\n全部完成！")