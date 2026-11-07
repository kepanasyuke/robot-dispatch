import { expect, test } from "@playwright/test";
import { loginAs } from "./session";

const MOCK = "http://127.0.0.1:8787";

test.beforeEach(async ({ page, request }) => {
  await loginAs(page);
  await request.post(`${MOCK}/__reset`);
});

test.describe("парк роботов", () => {
  test("показывает все карточки", async ({ page }) => {
    await page.goto("/#/robots");
    await expect(page.getByTestId("robot-card")).toHaveCount(3);
  });

  test("показывает статусы роботов", async ({ page }) => {
    await page.goto("/#/robots");
    const cards = page.getByTestId("robot-card");
    await expect(cards.getByText("Занят", { exact: true })).toBeVisible();
    await expect(cards.getByText("Свободен", { exact: true })).toBeVisible();
    await expect(cards.getByText("Не в сети", { exact: true })).toBeVisible();
  });

  test("считает роботов на связи", async ({ page }) => {
    await page.goto("/#/robots");
    await expect(page.getByText(/2 из 3 на связи/)).toBeVisible();
  });

  test("выделяет робота без связи", async ({ page }) => {
    await page.goto("/#/robots");
    const block = page.locator("section", { hasText: "Требуют внимания" });
    await expect(block.getByText("robot-3")).toBeVisible();
  });

  test("показывает namespace и возможности", async ({ page }) => {
    await page.goto("/#/robots");
    await expect(page.getByText("/robot1")).toBeVisible();
    await expect(page.getByText("heavy-lift")).toBeVisible();
  });

  test("не показывает ошибку при доступном API", async ({ page }) => {
    await page.goto("/#/robots");
    await expect(page.getByRole("alert")).toHaveCount(0);
  });
});

test.describe("навигация", () => {
  test("переключает вкладки", async ({ page }) => {
    await page.goto("/#/");
    await page.getByRole("link", { name: "Роботы" }).click();
    await expect(page).toHaveURL(/#\/robots/);

    await page.getByRole("link", { name: "Задачи" }).click();
    await expect(page).toHaveURL(/#\/tasks/);

    await page.getByRole("link", { name: "Обзор" }).click();
    await expect(page).toHaveURL(/#\/$/);
  });

  test("показывает страницу 404 для неизвестного маршрута", async ({ page }) => {
    await page.goto("/#/unknown-page");
    await expect(page.getByText("Страница не найдена")).toBeVisible();
  });
});
