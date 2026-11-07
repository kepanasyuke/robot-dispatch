import { describe, expect, it } from "vitest";
import { canCancelTasks, canCreateTasks, denyReason } from "./permissions";

describe("permissions", () => {
  it("оператор может создавать и отменять", () => {
    expect(canCreateTasks("operator")).toBe(true);
    expect(canCancelTasks("operator")).toBe(true);
  });

  it("наблюдатель не может создавать и отменять", () => {
    expect(canCreateTasks("viewer")).toBe(false);
    expect(canCancelTasks("viewer")).toBe(false);
  });

  it("объясняет отказ только наблюдателю", () => {
    expect(denyReason("viewer")).toContain("Наблюдатель");
    expect(denyReason("operator")).toBe("");
  });
});
