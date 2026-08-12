# 运行截图

本目录保存 2026-08-12 在本机 MySQL `bank_risk` 和真实 FastAPI 服务上采集的 8 张截图。
其中 `03_transfer_reject.png` 展示 U002/TXN_GEO_001 命中 R001 并由规则和模型共同拒绝。

复现方式：先启动服务，安装 Playwright 并准备 Chrome，然后运行
`node scripts/capture_screenshots.cjs`；非 Windows 环境通过 `BROWSER_PATH` 指定浏览器路径。
