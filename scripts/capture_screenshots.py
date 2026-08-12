"""
银行信贷风控 - 演示截图脚本 (Task 3 验收用)

用 Playwright 驱动本机 Edge 无头浏览器, 打开本地服务页面并截图,
覆盖 任务书 Task 3 验收的 3 大演示场景:
  风险检查 (表单 + 结果) / 案件管理 / 评估历史 (+ 仪表盘/规则/黑名单/Agent)

前置条件:
  1. Web 服务已启动: python run_app.py  (或 uvicorn scripts.main:app --port 8000)
  2. pip install playwright  (驱动已安装的 Edge, 无需下载浏览器内核)

跑法: python scripts/capture_screenshots.py
输出: screenshots/ 目录下 8 张 PNG
"""
import asyncio
import os
from pathlib import Path

from playwright.async_api import async_playwright

BASE_URL = os.getenv("APP_URL", "http://127.0.0.1:8000")
OUT_DIR = Path(__file__).resolve().parent.parent / "screenshots"


async def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)

        # 1. 仪表盘
        await page.goto(f"{BASE_URL}/", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT_DIR / "01-仪表盘.png"), full_page=True)
        print("01-仪表盘.png")

        # 2. 风险检查 - 表单
        await page.goto(f"{BASE_URL}/risk-check", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(OUT_DIR / "02-风险检查-表单.png"), full_page=True)
        print("02-风险检查-表单.png")

        # 3. 风险检查 - 执行结果 (团伙用户 U0003 贷款申请 LA0003 → 拒绝)
        await page.select_option("#ck_event_type", "贷款申请")
        await page.fill("#ck_user_id", "U0003")
        await page.fill("#ck_source_id", "LA0003")
        await page.click("#checkBtn")
        await page.wait_for_selector("#resultPanel", state="visible", timeout=20000)
        await page.wait_for_timeout(2500)
        await page.screenshot(path=str(OUT_DIR / "03-风险检查-结果.png"), full_page=True)
        print("03-风险检查-结果.png")

        # 4. 案件管理
        await page.goto(f"{BASE_URL}/cases", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT_DIR / "04-案件管理.png"), full_page=True)
        print("04-案件管理.png")

        # 5. 评估历史 (筛选 拒绝)
        await page.goto(f"{BASE_URL}/assessments", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT_DIR / "05-评估历史.png"), full_page=True)
        print("05-评估历史.png")

        # 6. 规则列表
        await page.goto(f"{BASE_URL}/rules", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT_DIR / "06-规则列表.png"), full_page=True)
        print("06-规则列表.png")

        # 7. 黑名单管理
        await page.goto(f"{BASE_URL}/blacklist", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT_DIR / "07-黑名单.png"), full_page=True)
        print("07-黑名单.png")

        # 8. AI Agent
        await page.goto(f"{BASE_URL}/chat", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT_DIR / "08-AI-Agent.png"), full_page=True)
        print("08-AI-Agent.png")

        await browser.close()
    print(f"\n截图完成, 输出目录: {OUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
