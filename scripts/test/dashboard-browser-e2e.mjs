/** Real browser acceptance of the deployed Snowflake Streamlit dashboard.
 *
 * Required environment:
 *   DASHBOARD_URL  deployed Streamlit URL
 *   DASHBOARD_PLAYWRIGHT_STORAGE_STATE  authenticated Snowflake browser state
 *
 * Run with a real browser, never a mocked Streamlit/Snowpark session:
 *   npx --yes playwright install chromium
 *   npx --yes -p playwright node scripts/test/dashboard-browser-e2e.mjs
 */
import { chromium } from "playwright";

const url = process.env.DASHBOARD_URL;
const storageState = process.env.DASHBOARD_PLAYWRIGHT_STORAGE_STATE;
if (!url || !storageState) {
  throw new Error("DASHBOARD_URL and DASHBOARD_PLAYWRIGHT_STORAGE_STATE are required");
}

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ storageState });
const page = await context.newPage();
try {
  await page.goto(url, { waitUntil: "networkidle", timeout: 90_000 });
  await page.getByText("Company 360", { exact: true }).click();
  const search = page.getByPlaceholder("e.g. AAPL, Apple, or 320193");
  await search.fill("AAPL");
  await page.waitForTimeout(1_000);
  await page.getByText(/APPLE.*CIK 320193/i).first().waitFor({ timeout: 30_000 });
  await page.getByText("Fundamentals Screener", { exact: true }).click();
  const fundamentals = page.getByPlaceholder("e.g. AAPL, Apple, or 320193").last();
  await fundamentals.fill("AAPL");
  await page.getByText(/APPLE.*CIK 320193/i).last().waitFor({ timeout: 30_000 });
  await page.getByText("Insider Watch", { exact: true }).click();
  const insider = page.getByPlaceholder("e.g. AAPL, Apple, or 320193").last();
  await insider.fill("ZZZZ");
  await page.getByText("No SEC company matched 'ZZZZ'. Try ticker, company name, or CIK.").waitFor({ timeout: 30_000 });
} finally {
  await browser.close();
}
