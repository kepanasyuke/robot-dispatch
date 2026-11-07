import { expect, test } from "@playwright/test";
import { loginAs } from "./session";

const MOCK = "http://127.0.0.1:8787";

test.beforeEach(async ({ page, request }) => {
  await loginAs(page);
  await request.post(`${MOCK}/__reset`);
});

test.describe("список задач", () => {
  test("показывает все задачи", async ({ page }) => {
    await page.goto("/#/tasks");
    await expect(page.getByTestId("task-row")).toHaveCount(6);
  });

  test("фильтрует по статусу", async ({ page }) => {
    await page.goto("/#/tasks");
    await page.getByRole("button", { name: "Провалена" }).click();

    await expect(page.getByTestId("task-row")).toHaveCount(1);
    await expect(page.getByText("battery critical")).toBeVisible();
  });

  test("снимает фильтр по статусу", async ({ page }) => {
    await page.goto("/#/tasks");
    const chip = page.getByRole("button", { name: "Провалена" });
    await chip.click();
    await expect(page.getByTestId("task-row")).toHaveCount(1);
    await chip.click();
    await expect(page.getByTestId("task-row")).toHaveCount(6);
  });

  test("фильтрует по типу", async ({ page }) => {
    await page.goto("/#/tasks");
    await page.getByLabel("Тип задачи").selectOption("inventory");
    await expect(page.getByTestId("task-row")).toHaveCount(2);
  });

  test("ищет по тексту", async ({ page }) => {
    await page.goto("/#/tasks");
    await page.getByLabel("Поиск по задачам").fill("wms-0998");
    await expect(page.getByTestId("task-row")).toHaveCount(1);
  });

  test("показывает пустое состояние при пустом поиске", async ({ page }) => {
    await page.goto("/#/tasks");
    await page.getByLabel("Поиск по задачам").fill("нет-такой-задачи");
    await expect(page.getByText("Задач нет")).toBeVisible();
  });

  test("сбрасывает фильтры", async ({ page }) => {
    await page.goto("/#/tasks");
    await page.getByRole("button", { name: "Провалена" }).click();
    await page.getByRole("button", { name: "Сбросить" }).click();
    await expect(page.getByTestId("task-row")).toHaveCount(6);
  });

  test("открывает карточку задачи", async ({ page }) => {
    await page.goto("/#/tasks");
    await page.getByRole("link", { name: "delivery" }).first().click();

    await expect(page).toHaveURL(/#\/tasks\/[0-9a-f-]+/);
    await expect(page.getByText("История событий")).toBeVisible();
  });
});
