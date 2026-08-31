import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";

const outputDir = "video/build/browser";
await mkdir(outputDir, { recursive: true });
await mkdir("assets", { recursive: true });

const executablePath = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const browser = await chromium.launch({ headless: true, executablePath });
const demoUrl = process.env.PERMITDIFF_DEMO_URL || "https://permitdiff.vercel.app/";
const evidenceUrl =
  process.env.PERMITDIFF_EVIDENCE_URL ||
  "https://yangyangnovelist-hub.github.io/permitdiff-calle/";

const stillContext = await browser.newContext({
  viewport: { width: 1200, height: 800 },
  colorScheme: "light",
});
const stillPage = await stillContext.newPage();
await stillPage.goto(demoUrl, { waitUntil: "networkidle" });
await stillPage.screenshot({ path: "assets/permitdiff-cover.png" });
await stillPage.getByRole("button", { name: "Stale + discrepancy" }).click();
await stillPage.screenshot({ path: "assets/permitdiff-discrepancy.png" });
await stillContext.close();

const context = await browser.newContext({
  viewport: { width: 1280, height: 720 },
  recordVideo: { dir: outputDir, size: { width: 1280, height: 720 } },
  colorScheme: "light",
});
const page = await context.newPage();
const video = page.video();
const pause = (seconds) => page.waitForTimeout(seconds * 1000);

await page.goto(demoUrl, { waitUntil: "networkidle" });
await pause(14);
await page.getByRole("button", { name: "Fresh record" }).click();
await pause(12);
await page.getByRole("button", { name: "Stale + match" }).click();
await pause(15);
await page.getByRole("button", { name: "Stale + discrepancy" }).click();
await pause(20);

await page.goto(evidenceUrl, { waitUntil: "networkidle" });
await pause(12);
await page.locator("#fresh").click();
await page.locator("#evaluate").click();
await pause(12);
await page.locator("#conflict").click();
await page.locator('[data-scenario="discrepancy"]').click();
await pause(18);

await page.goto(
  "https://github.com/yangyangnovelist-hub/permitdiff-calle/blob/main/artifacts/example-preview.json",
  { waitUntil: "domcontentloaded" },
);
await pause(15);
await page.goto("https://github.com/CALLE-AI/awesome-phone-call-agents/pull/199", {
  waitUntil: "domcontentloaded",
});
await pause(18);
await page.goto("https://github.com/yangyangnovelist-hub/permitdiff-calle", {
  waitUntil: "domcontentloaded",
});
await pause(20);

await page.close();
await context.close();
console.log(await video.path());
await browser.close();
