import { expect, test } from "@playwright/test";
import { loginAs } from "./session";

const MOCK = "http://127.0.0.1:8787";

test.beforeEach(async ({ page, request }) => {
  await loginAs(page);
  const response = await request.post(`${MOCK}/__reset`);
  expect(response.ok()).toBeTruthy();
});

test.describe("обзор флота", () => {
  test("показывает заголовок и KPI", async ({ page }) => {
    await page.goto("/#/");

    await expect(page.getByText("Robot Dispatch")).toBeVisible();
    await expect(page.getByText("Задач всего")).toBeVisible();
    await expect(page.getByText("6", { exact: true }).first()).toBeVisible();
  });

  test("сообщает состояние сервиса", async ({ page }) => {
    await page.goto("/#/");
    await expect(page.getByRole("banner").getByText("Всё в порядке")).toBeVisible();
  });

  test("показывает очередь по статусам", async ({ page }) => {
    await page.goto("/#/");
    const panel = page.locator("section", { hasText: "Очередь по статусам" });
    await expect(panel.getByText("В очереди")).toBeVisible();
    await expect(panel.getByText("Провалена")).toBeVisible();
  });

  test("показывает роботов на обзоре", async ({ page }) => {
    await page.goto("/#/");
    await expect(page.getByTestId("robot-card")).toHaveCount(3);
    await expect(page.getByText("robot-1")).toBeVisible();
  });

  test("переходит на вкладку задач", async ({ page }) => {
    await page.goto("/#/");
    await page.getByRole("link", { name: "Задачи" }).click();
    await expect(page).toHaveURL(/#\/tasks/);
    await expect(page.getByRole("heading", { name: "Задачи" })).toBeVisible();
  });
});
