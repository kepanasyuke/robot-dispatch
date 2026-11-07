import { expect, test } from "@playwright/test";

const MOCK = "http://127.0.0.1:8787";
const RUNNING = "aaaa1111-1111-4111-8111-111111111111";
const PENDING = "aaaa2222-2222-4222-8222-222222222222";
const RETRYING = "aaaa3333-3333-4333-8333-333333333333";

test.beforeEach(async ({ request }) => {
  await request.post(`${MOCK}/__reset`);
});

test.describe("карточка задачи", () => {
  test("показывает поля выполняющейся задачи", async ({ page }) => {
    await page.goto(`/#/tasks/${RUNNING}`);

    await expect(page.getByText("Выполняется")).toBeVisible();
    await expect(page.getByText(RUNNING)).toBeVisible();
    await expect(page.getByText("200")).toBeVisible();
    await expect(page.getByText("2 минуты")).toBeVisible();
  });

  test("показывает историю событий", async ({ page }) => {
    await page.goto(`/#/tasks/${RUNNING}`);
    await expect(page.getByTestId("timeline-item")).toHaveCount(3);
    await expect(page.getByText("Задача создана")).toBeVisible();
    await expect(page.getByText("Назначена роботу")).toBeVisible();
  });

  test("показывает путь переходов", async ({ page }) => {
    await page.goto(`/#/tasks/${RUNNING}`);
    await expect(page.getByText("pending → assigned → running")).toBeVisible();
  });

  test("отказ отмены выполняющейся задачи виден пользователю", async ({ page }) => {
    await page.goto(`/#/tasks/${RUNNING}`);
    await page.getByRole("button", { name: "Отменить" }).click();

    await expect(page.getByRole("alert")).toContainText("running tasks cannot be cancelled");
  });

  test("отменяет задачу из очереди", async ({ page }) => {
    await page.goto(`/#/tasks/${PENDING}`);
    await page.getByRole("button", { name: "Отменить" }).click();

    await expect(page.getByText("Отменена").first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Завершена" })).toBeDisabled();
  });

  test("показывает ошибку и повторы", async ({ page }) => {
    await page.goto(`/#/tasks/${RETRYING}`);

    await expect(page.getByText("Повтор").first()).toBeVisible();
    await expect(page.getByText("lease expired: robot did not report progress")).toBeVisible();
    await expect(page.getByText(/Повторы по событиям/)).toBeVisible();
  });

  test("показывает payload", async ({ page }) => {
    await page.goto(`/#/tasks/${RUNNING}`);
    await page.getByText("Payload").click();
    await expect(page.getByText(/"weight_kg": 12/)).toBeVisible();
  });

  test("возвращает к списку задач", async ({ page }) => {
    await page.goto(`/#/tasks/${RUNNING}`);
    await page.getByRole("link", { name: "← ко всем задачам" }).click();
    await expect(page).toHaveURL(/#\/tasks$/);
  });

  test("показывает ошибку для неизвестной задачи", async ({ page }) => {
    await page.goto("/#/tasks/00000000-0000-0000-0000-000000000000");
    await expect(page.getByRole("alert")).toContainText("not found");
  });
});
