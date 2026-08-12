/* 采集真实运行截图。先启动服务，再执行：node scripts/capture_screenshots.cjs */
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const baseUrl = process.env.APP_BASE_URL || 'http://127.0.0.1:8000';
const outDir = path.resolve(__dirname, '..', 'docs', 'screenshots');

async function capture(page, route, filename) {
  await page.goto(baseUrl + route, { waitUntil: 'networkidle' });
  await page.screenshot({ path: path.join(outDir, filename), fullPage: true });
}

(async () => {
  fs.mkdirSync(outDir, { recursive: true });
  const browserPath = process.env.BROWSER_PATH
    || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
  const browser = await chromium.launch({ headless: true, executablePath: browserPath });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await capture(page, '/', '01_dashboard.png');
  await capture(page, '/rules', '02_rules.png');

  await page.goto(baseUrl + '/risk-check', { waitUntil: 'networkidle' });
  await page.selectOption('#ck_event_type', '转账');
  await page.fill('#ck_user_id', 'U002');
  await page.fill('#ck_source_id', 'TXN_GEO_001');
  await page.click('#checkBtn');
  await page.waitForSelector('#resultPanel', { state: 'visible' });
  await page.screenshot({ path: path.join(outDir, '03_transfer_reject.png'), fullPage: true });

  await page.selectOption('#ck_event_type', '贷款');
  await page.fill('#ck_user_id', 'U006');
  await page.fill('#ck_source_id', 'LOAN_MULTI_1');
  await page.click('#checkBtn');
  await page.waitForSelector('#resultPanel', { state: 'visible' });
  await page.screenshot({ path: path.join(outDir, '04_loan_review.png'), fullPage: true });

  await page.selectOption('#ck_event_type', '登录');
  await page.fill('#ck_user_id', 'U008');
  await page.fill('#ck_source_id', 'LOGIN_PROXY');
  await page.click('#checkBtn');
  await page.waitForSelector('#resultPanel', { state: 'visible' });
  await page.screenshot({ path: path.join(outDir, '05_login_proxy.png'), fullPage: true });

  await capture(page, '/cases', '06_case_detail.png');
  await capture(page, '/blacklist', '07_blacklist.png');
  await capture(page, '/chat', '08_agent.png');
  await browser.close();
  console.log(`screenshots=${outDir}`);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
