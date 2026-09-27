import { aircraft, clickLonLat, DEFAULT_PREFERENCES, expect, layerRow, test } from "./fixtures";

test("a flight track can be shown and hidden from the inspector", async ({ page, api }) => {
  api.set({
    aircraft: [aircraft("3c6444", 48.85, 2.35)],
    preferences: {
      ...DEFAULT_PREFERENCES,
      enabled_layers: ["aircraft"],
      viewport: { center: { lat: 48.85, lon: 2.35 }, zoom: 6 },
    },
  });
  await page.goto("/");
  await expect(page.getByTitle("Hide Live flights")).toContainText("1");
  await clickLonLat(page, 2.35, 48.85);

  const inspector = page.getByRole("complementary", { name: "Inspector" });
  const requested = page.waitForRequest((r) => r.url().endsWith("/aviation/aircraft/3c6444/track"));
  await inspector.getByRole("button", { name: "Show track" }).click();
  await requested;
  await expect(inspector.getByRole("button", { name: "Hide track" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  const drawn = await page.evaluate(
    () => window.__argusMap?.querySourceFeatures("argus-track").length ?? 0,
  );
  expect(drawn).toBeGreaterThan(0);

  await inspector.getByRole("button", { name: "Hide track" }).click();
  await expect(inspector.getByRole("button", { name: "Show track" })).toBeVisible();
});

test("the 3D globe is toggled and remembered", async ({ page }) => {
  await page.goto("/");
  const saved = page.waitForRequest(
    (r) => r.method() === "PUT" && r.url().endsWith("/preferences"),
  );
  await page.getByRole("button", { name: "3D" }).click();
  expect((await saved).postDataJSON().projection).toBe("globe");
  await expect(page.getByRole("button", { name: "3D" })).toHaveAttribute("aria-pressed", "true");
  const projection = await page.evaluate(() => window.__argusMap?.getProjection()?.type);
  expect(projection).toBe("globe");
});

test("a saved globe projection is restored", async ({ page, api }) => {
  api.set({ preferences: { ...DEFAULT_PREFERENCES, projection: "globe" } });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "3D" })).toHaveAttribute("aria-pressed", "true");
});

test("OSM layers wait for the user to zoom in", async ({ page, api }) => {
  api.set({
    preferences: {
      ...DEFAULT_PREFERENCES,
      enabled_layers: ["facility-military"],
      viewport: { center: { lat: 48, lon: 10 }, zoom: 3 },
    },
  });
  await page.goto("/");
  const row = await layerRow(page, "Military sites (OSM)");
  await expect(row).toContainText("Zoom in to load");
  expect(api.calls("GET", "/infrastructure/facilities/military")).toHaveLength(0);

  await page.evaluate(() => window.__argusMap?.jumpTo({ zoom: 6 }));
  await expect(row).toContainText("Updated");
  expect(api.calls("GET", "/infrastructure/facilities/military").length).toBeGreaterThan(0);
});
