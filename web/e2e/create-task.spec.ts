import { expect, test } from "@playwright/test";
import { loginAs } from "./session";

const MOCK = "http://127.0.0.1:8787";

test.beforeEach(async ({ page, request }) => {
  await loginAs(page);
  await request.post(`${MOCK}/__reset`);
});

test.describe("создание задачи", () => {
  test("открывает форму", async ({ page }) => {
    await page.goto("/#/tasks");
    await page.getByRole("button", { name: "Новая задача" }).click();

    await expect(page.getByRole("dialog", { name: "Новая задача" })).toBeVisible();
  });

  test("создаёт задачу и показывает её в списке", async ({ page }) => {
    await page.goto("/#/tasks");
    await expect(page.getByTestId("task-row")).toHaveCount(6);

    await page.getByRole("button", { name: "Новая задача" }).click();
    const dialog = page.getByRole("dialog", { name: "Новая задача" });
    await dialog.getByLabel("Тип").fill("patrol");
    await dialog.getByLabel(/Приоритет/).fill("300");
    await dialog.getByLabel("Payload (JSON)").fill('{"zone":"K"}');
    await dialog.getByRole("button", { name: "Создать" }).click();

    await expect(dialog).toBeHidden();
    await expect(page.getByTestId("task-row")).toHaveCount(7);
    await expect(page.getByRole("link", { name: "patrol" })).toBeVisible();
  });

  test("показывает ошибку валидации с сервера", async ({ page }) => {
    await page.goto("/#/tasks");
    await page.getByRole("button", { name: "Новая задача" }).click();

    await page.route("**/api/v1/tasks", async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 422,
          contentType: "application/json",
          body: JSON.stringify({ detail: [{ loc: ["body", "priority"], msg: "too big" }] }),
        });
        return;
      }
      await route.continue();
    });

    const dialog = page.getByRole("dialog", { name: "Новая задача" });
    await dialog.getByLabel("Тип").fill("delivery");
    await dialog.getByRole("button", { name: "Создать" }).click();

    await expect(dialog.getByRole("alert")).toContainText("код 422");
  });

  test("закрывается без создания", async ({ page }) => {
    await page.goto("/#/tasks");
    await page.getByRole("button", { name: "Новая задача" }).click();
    await page.getByRole("button", { name: "Отмена" }).click();

    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByTestId("task-row")).toHaveCount(6);
  });

  test("блокирует отправку с битым JSON", async ({ page }) => {
    await page.goto("/#/tasks");
    await page.getByRole("button", { name: "Новая задача" }).click();

    const dialog = page.getByRole("dialog", { name: "Новая задача" });
    await dialog.getByLabel("Тип").fill("delivery");
    await dialog.getByLabel("Payload (JSON)").fill("{oops");

    await expect(dialog.getByText("Payload не является валидным JSON")).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Создать" })).toBeDisabled();
  });
});
