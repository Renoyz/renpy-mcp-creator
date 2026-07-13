import { describe, expect, it } from "vitest";
import { findFreePort } from "./ports";

describe("findFreePort", () => {
  it("returns an available loopback port", async () => {
    const port = await findFreePort();

    expect(Number.isInteger(port)).toBe(true);
    expect(port).toBeGreaterThan(0);
    expect(port).toBeLessThanOrEqual(65535);
  });
});
