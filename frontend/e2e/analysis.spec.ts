import { DEFAULT_PREFERENCES, expect, layerRow, test } from "./fixtures";

test("the countries space ranks scores and is honest about its limits", async ({ page }) => {
  await page.goto("/#countries");
  const main = page.getByRole("main", { name: "Countries" });
  await expect(main).toContainText("not a measure of a country's stability");
  await expect(main).toContainText("No baseline yet");
  const rows = main.locator(".country-row");
  await expect(rows.first()).toContainText("Ukraine");
  await expect(rows.first().getByRole("meter")).toHaveAttribute("value", "63.3");
});

test("a country page explains every point and shows its history", async ({ page }) => {
  await page.goto("/#countries/UA");
  const main = page.getByRole("main", { name: "Countries" });
  await expect(
    main.getByRole("region", { name: "Ukraine", exact: true }).getByRole("heading", { level: 2 }),
  ).toHaveText("Ukraine");
  await expect(main.locator(".tile", { hasText: "Reported violence" })).toContainText("33");
  await expect(main.locator(".tile", { hasText: "Air-raid alerts" })).toContainText("15");
  await expect(main.getByRole("img", { name: /Score over the last/ })).toBeVisible();
  await expect(main.getByText(/2 hourly snapshots/)).toBeVisible();
  await expect(main.getByRole("region", { name: "Summary" })).toContainText(
    "Computed without: news.",
  );
  await expect(main.getByRole("link", { name: /Strait of Hormuz/ })).toBeVisible();
  await main.locator(".country-row", { hasText: "Iran" }).click();
  await expect(page).toHaveURL(/#countries\/IR$/);
});

test("a country can be followed", async ({ page }) => {
  await page.goto("/#countries/UA");
  const created = page.waitForRequest(
    (r) => r.method() === "POST" && r.url().endsWith("/watchlists"),
  );
  await page.getByRole("button", { name: "☆ Follow" }).click();
  expect((await created).postDataJSON().items).toEqual([
    { kind: "country", value: "UA", label: "Ukraine" },
  ]);
  await expect(page.getByRole("button", { name: "★ Following" })).toBeVisible();
});

test("situations list convergences, never counting press reports as corroboration", async ({
  page,
}) => {
  await page.goto("/");
  await page.waitForFunction(() => window.__argusMap?.loaded());
  const panel = page.getByRole("complementary", { name: "Right now" });
  await expect(panel).toContainText("A reason to look, not a conclusion");
  await expect(panel).toContainText("Computed without: fires");
  await expect(panel.getByRole("heading", { name: "Air-raid alert" })).toBeVisible();
  await expect(panel).toContainText("One verified kind, plus unverified reports");
  await panel.getByRole("button", { name: "Focus Ukraine · 49.2°, 33.1°" }).click();
  await page.waitForFunction(() => {
    const c = window.__argusMap?.getCenter();
    return c !== undefined && Math.abs(c.lat - 49.2) < 0.5 && Math.abs(c.lng - 33.1) < 0.5;
  });
  await expect(panel.getByRole("button", { name: "Focus Ukraine · 49.2°, 33.1°" })).toHaveText(
    "In focus",
  );
});

test("the choropleth colours countries from the index", async ({ page, api }) => {
  api.set({
    preferences: {
      ...DEFAULT_PREFERENCES,
      enabled_layers: ["country-index"],
      viewport: { center: { lat: 45, lon: 30 }, zoom: 2 },
    },
  });
  await page.goto("/");
  await expect(await layerRow(page, "Country Signal Index")).toContainText("175");
  const scored = await page.evaluate(() =>
    (window.__argusMap?.querySourceFeatures("argus-src-country-index") ?? [])
      .filter((f) => Number(f.properties?.score) > 0)
      .map((f) => f.properties?.iso2),
  );
  expect(new Set(scored)).toEqual(new Set(["UA", "IR"]));
});
