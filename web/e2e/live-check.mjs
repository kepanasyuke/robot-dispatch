import { chromium } from "playwright";

const base = "https://kepanasyuke.github.io/robot-dispatch/dispatch/";
const results = [];
const check = (name, ok, extra = "") => {
  results.push(`${ok ? "PASS" : "FAIL"} ${name}${extra ? " — " + extra : ""}`);
  return ok;
};

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
page.on("requestfailed", (request) => errors.push(`requestfailed ${request.url()}`));

try {
  await page.goto(base, { waitUntil: "networkidle", timeout: 45000 });
  check("страница входа открылась", await page.getByRole("form", { name: "Вход в консоль" }).isVisible());

  await page.getByRole("button", { name: "Войти" }).click();
  await page.getByText("Задач всего").waitFor({ timeout: 15000 });
  check("демо-данные загрузились", (await page.getByTestId("robot-card").count()) === 3, "3 робота");

  await page.getByRole("link", { name: "Задачи" }).click();
  await page.waitForTimeout(500);
  const rows = await page.getByTestId("task-row").count();
  check("вкладка задач", rows === 5, `строк: ${rows}`);

  await page.goto(`${base}#/tasks`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  check("deep link #/tasks", (await page.getByTestId("task-row").count()) === 5);

  await page.goto(`${base}#/tasks/demo-running-0001`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  check("deep link на карточку", await page.getByText("История событий").isVisible());

  await page.goto(`${base}#/robots`, { waitUntil: "networkidle" });
  await page.waitForTimeout(400);
  check("deep link #/robots", (await page.getByTestId("robot-card").count()) === 3);

  await page.getByRole("button", { name: "Новая задача" }).count();
  await page.goto(`${base}#/tasks`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Новая задача" }).click();
  check("форма создания открывается", await page.getByRole("dialog").isVisible());
  await page.getByRole("button", { name: "Отмена" }).click();

  check("нет ошибок в консоли", errors.length === 0, errors.join("; ").slice(0, 200));
} catch (error) {
  check("сценарий без исключений", false, String(error).slice(0, 300));
} finally {
  await browser.close();
}

console.log(results.join("\n"));
process.exit(results.some((line) => line.startsWith("FAIL")) ? 1 : 0);
