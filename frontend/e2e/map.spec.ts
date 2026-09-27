import { aircraft, DEFAULT_PREFERENCES, expect, layerRow, test } from "./fixtures";

const SKY = [aircraft("aaaaa1", 48.85, 2.35), aircraft("bbbbb2", 48.9, 2.4)];

test.describe("map", () => {
  test("shows live flights and a healthy status", async ({ page, api }) => {
    api.set({ aircraft: SKY });
    await page.goto("/");

    const flights = await layerRow(page, "Live flights");
    await expect(flights).toHaveAttribute("aria-pressed", "true");
    await expect(flights).toContainText("2");
    await expect(page.getByRole("status")).toHaveText("● Live");
    await expect(page.getByTestId("map").locator("canvas")).toBeVisible();

    const [request] = api.calls("GET", "/aviation/aircraft");
    expect(new URL(request?.url() ?? "").searchParams.get("bbox")).toMatch(
      /^-?\d+\.\d{4}(,-?\d+\.\d{4}){3}$/,
    );
  });

  test("restores saved layers and viewport", async ({ page, api }) => {
    api.set({
      aircraft: SKY,
      preferences: {
        ...DEFAULT_PREFERENCES,
        enabled_layers: [],
        viewport: { center: { lat: 35.68, lon: 139.69 }, zoom: 8 },
      },
    });
    await page.goto("/");

    await expect(await layerRow(page, "Live flights")).toHaveAttribute("aria-pressed", "false");
    await page.waitForTimeout(500);
    expect(api.calls("GET", "/aviation/aircraft")).toHaveLength(0);
  });

  test("toggling a layer is persisted", async ({ page, api }) => {
    api.set({ aircraft: SKY });
    await page.goto("/");
    const flights = await layerRow(page, "Live flights");
    await expect(flights).toHaveAttribute("aria-pressed", "true");

    const saved = page.waitForRequest(
      (r) => r.method() === "PUT" && r.url().endsWith("/api/v1/preferences"),
    );
    await flights.click();
    const body = (await saved).postDataJSON();
    // The other default layers stay on; only flights were switched off.
    expect(body).toEqual({
      schema_version: 1,
      enabled_layers: ["earthquakes", "sat-stations"],
      viewport: null,
      projection: null,
      telegram_channels: null,
    });
    await expect(flights).toHaveAttribute("aria-pressed", "false");
  });

  test("active layers show as pills that hide them", async ({ page, api }) => {
    api.set({ aircraft: SKY });
    await page.goto("/");
    const pill = page.getByTitle("Hide Live flights");
    await expect(pill).toContainText("2");
    await pill.click();
    await expect(pill).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^Layers · 2$/ })).toBeVisible();
  });

  test("panning the map persists the viewport once, debounced", async ({ page, api }) => {
    api.set({ aircraft: SKY });
    await page.goto("/");
    await expect(page.getByTitle("Hide Live flights")).toContainText("2");

    const box = await page.getByTestId("map").boundingBox();
    if (!box) throw new Error("map not rendered");
    const saved = page.waitForRequest(
      (r) => r.method() === "PUT" && r.url().endsWith("/api/v1/preferences"),
    );
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 - 200, box.y + box.height / 2, { steps: 5 });
    await page.mouse.up();

    const { viewport } = (await saved).postDataJSON();
    expect(viewport.center.lon).toBeGreaterThan(20);
    expect(viewport.zoom).toBe(2);
    await page.waitForTimeout(1_500);
    expect(api.calls("PUT", "/preferences")).toHaveLength(1);
  });

  test("still starts with defaults when preferences cannot be loaded", async ({ page, api }) => {
    api.set({ aircraft: SKY, preferences: "error" });
    await page.goto("/");
    const flights = await layerRow(page, "Live flights");
    await expect(flights).toHaveAttribute("aria-pressed", "true");
    await expect(flights).toContainText("2");
  });

  test("says Offline when the API is unreachable", async ({ page, api }) => {
    api.set({ health: "error" });
    await page.goto("/");
    await expect(page.getByRole("status")).toHaveText("■ Offline");
  });

  test("a region preset moves the camera", async ({ page }) => {
    await page.goto("/");
    await page.waitForFunction(() => window.__argusMap?.loaded());
    await page.getByRole("button", { name: "Taiwan" }).click();
    await expect(page.getByRole("button", { name: "Taiwan" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.waitForFunction(() => {
      const c = window.__argusMap?.getCenter();
      return c !== undefined && Math.abs(c.lat - 23.5) < 2 && Math.abs(c.lng - 121) < 2;
    });
  });
});
