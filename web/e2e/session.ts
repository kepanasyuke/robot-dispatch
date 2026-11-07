import type { Page } from "@playwright/test";

export type Role = "operator" | "viewer";

export async function loginAs(page: Page, role: Role = "operator"): Promise<void> {
  const session = JSON.stringify({ role, apiKey: "" });
  await page.goto("/");
  await page.evaluate((value: string) => {
    window.sessionStorage.setItem("dispatch.session", value);
  }, session);
  await page.reload();
}
