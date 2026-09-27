import { DEFAULT_PREFERENCES, expect, layerRow, test } from "./fixtures";

test("the markets space shows delayed quotes, grouped, with a chart", async ({ page }) => {
  await page.goto("/");
  await page
    .getByRole("navigation", { name: "Spaces" })
    .getByRole("button", { name: "Markets" })
    .click();
  await expect(page).toHaveURL(/#markets$/);
  const main = page.getByRole("main", { name: "Markets" });
  await expect(main).toContainText("Delayed prices");
  await expect(main.getByRole("region", { name: "Market note" })).toContainText(
    "figures by Argus, no model",
  );
  const brent = main.getByRole("row", { name: /Brent crude/ });
  await expect(brent).toContainText("97.44");
  await expect(brent).toContainText("▼ 8.59 %"); // the arrow, not only the colour
  await expect(main.locator("tr.group-row", { hasText: "Energy" })).toBeVisible();
  await expect(main).toContainText("Missing right now: ^N225");

  const chart = main.getByRole("region", { name: "Brent crude chart" });
  await expect(chart.getByRole("img", { name: /daily closes/ })).toBeVisible();
  await expect(chart).toContainText("Resistance110.20 (3×)");
  await expect(chart).toContainText("RSI 1471");
  await expect(chart).toContainText("Descriptive, not a forecast");

  await main.getByRole("button", { name: "Crypto" }).click();
  await expect(main.getByRole("row", { name: /Bitcoin/ })).toBeVisible();
  await expect(main.getByRole("row", { name: /Brent crude/ })).toHaveCount(0);
});

test("choosing an instrument loads its history and is kept in the URL", async ({ page, api }) => {
  await page.goto("/#markets");
  const main = page.getByRole("main", { name: "Markets" });
  await main.getByRole("row", { name: /Bitcoin/ }).click();
  await expect(page).toHaveURL(/#markets\/BTC-USD$/);
  await expect(main.getByRole("region", { name: "Bitcoin chart" })).toBeVisible();
  await main.getByRole("button", { name: "1Y" }).click();
  await expect
    .poll(
      () => api.requests.filter((r) => r.url().includes("/markets/assets/BTC-USD?range=1y")).length,
    )
    .toBeGreaterThan(0);
});

test("macro, energy, derivatives and blocked sources are explained", async ({ page }) => {
  await page.goto("/#markets");
  const main = page.getByRole("main", { name: "Markets" });
  await expect(main).toContainText("inverted");
  await expect(main).toContainText("Crypto Fear & Greed");
  await expect(main).toContainText("Non-Farm Employment Change");
  await expect(main).toContainText("BTC funding");
  await expect(main).toContainText("OKX only, a sample");
  await expect(main).toContainText("Strategic Petroleum Reserve");
  await expect(main).toContainText("Missing: natural gas");
  // Blocked upstream: explained, not worked around.
  await expect(main).toContainText("Polymarket is unreachable from this server");
});

test("a chokepoint opens on the map with its layer", async ({ page }) => {
  await page.goto("/#markets");
  const main = page.getByRole("main", { name: "Markets" });
  await expect(main).toContainText("Traffic near zero");
  await main.getByRole("button", { name: /Strait of Hormuz/ }).click();
  await expect(page).toHaveURL(/\/$|\/#?$/);
  await page.waitForFunction(() => {
    const c = window.__argusMap?.getCenter();
    return c !== undefined && Math.abs(c.lat - 26.6) < 0.5 && Math.abs(c.lng - 56.3) < 0.5;
  });
  await expect(await layerRow(page, "Chokepoint traffic")).toHaveAttribute("aria-pressed", "true");
});

test("the chokepoint layer puts traffic on the map", async ({ page, api }) => {
  api.set({
    preferences: {
      ...DEFAULT_PREFERENCES,
      enabled_layers: ["chokepoints"],
      viewport: { center: { lat: 26.6, lon: 56.3 }, zoom: 4 },
    },
  });
  await page.goto("/");
  await page.waitForFunction(
    () => window.__argusMap?.getLayer("argus-lyr-chokepoints") !== undefined,
  );
  await expect.poll(() => api.calls("GET", "/maritime/chokepoints").length).toBeGreaterThan(0);
});
