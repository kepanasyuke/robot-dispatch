import { test } from "@playwright/test";
import { mkdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const docs = join(here, "..", "..", "docs");
const screens = join(docs, "screens");
const frames = join(docs, "frames");
const MOCK = "http://127.0.0.1:8787";
const PENDING = "aaaa2222-2222-4222-8222-222222222222";

test.describe.configure({ mode: "serial" });

test.beforeAll(() => {
  mkdirSync(screens, { recursive: true });
  rmSync(frames, { recursive: true, force: true });
  mkdirSync(frames, { recursive: true });
});

test.beforeEach(async ({ request }) => {
  await request.post(`${MOCK}/__reset`);
});

test("снимки экранов", async ({ page }) => {
  const shots: Array<[string, string]> = [
    ["/#/", "01-dashboard.png"],
    ["/#/tasks", "02-tasks.png"],
    ["/#/tasks/aaaa1111-1111-4111-8111-111111111111", "03-task-detail.png"],
    ["/#/robots", "04-robots.png"],
  ];

  for (const [route, name] of shots) {
    await page.goto(route);
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: join(screens, name), fullPage: true });
  }
});

test("кадры для гифки", async ({ page }) => {
  let index = 0;
  const frame = async () => {
    index += 1;
    await page.screenshot({ path: join(frames, `frame-${String(index).padStart(3, "0")}.png`) });
  };

  await page.goto("/#/tasks");
  await page.waitForLoadState("networkidle");
  await frame();

  await page.getByRole("button", { name: "Провалена" }).click();
  await frame();

  await page.getByRole("button", { name: "Сбросить" }).click();
  await page.getByLabel("Поиск по задачам").fill("wms");
  await frame();

  await page.getByLabel("Поиск по задачам").fill("");
  await page.getByRole("link", { name: "delivery" }).first().click();
  await page.waitForLoadState("networkidle");
  await frame();

  await page.getByText("Payload").click();
  await frame();

  await page.getByRole("link", { name: "← ко всем задачам" }).click();
  await page.goto(`/#/tasks/${PENDING}`);
  await page.waitForLoadState("networkidle");
  await frame();

  await page.getByRole("button", { name: "Отменить" }).click();
  await page.waitForTimeout(400);
  await frame();

  await page.goto("/#/robots");
  await page.waitForLoadState("networkidle");
  await frame();
});
