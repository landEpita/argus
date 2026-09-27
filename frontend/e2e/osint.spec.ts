import {
  aircraft,
  clickLonLat,
  DEFAULT_PREFERENCES,
  earthquake,
  expect,
  layerRow,
  test,
} from "./fixtures";

test("default event and space layers load alongside flights", async ({ page, api }) => {
  api.set({
    aircraft: [aircraft("aaaaa1", 48.85, 2.35)],
    earthquakes: [earthquake("1", 48.5, 2.0, 5.1), earthquake("2", 48.6, 2.1, 3.2)],
  });
  await page.goto("/");
  await expect(await layerRow(page, "Earthquakes (24 h)")).toContainText("2");
  await expect(await layerRow(page, "Space stations")).toContainText("0");
  expect(api.calls("GET", "/events/earthquakes")[0]?.url()).toContain("since_hours=24");
});

test("recent events fill the six-hour histogram", async ({ page, api }) => {
  api.set({ earthquakes: [earthquake("1", 48.5, 2.0, 5.1)] });
  await page.goto("/");
  await expect(page.getByRole("region", { name: "Events in the last 6 hours" })).toContainText(
    "1 events on screen",
  );
});

test("a layer the server cannot serve says so and stops polling", async ({ page, api }) => {
  await page.goto("/");
  const ships = await layerRow(page, "Ships (AIS)");
  await ships.click();
  await expect(ships).toContainText("Not configured on the server");
  await expect(page.getByRole("button", { name: "Add API key…" })).toBeVisible();
  await page.waitForTimeout(1_000);
  expect(api.calls("GET", "/maritime/vessels")).toHaveLength(1);
});

test("an aircraft can be watched from the inspector", async ({ page, api }) => {
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
  await expect(inspector.getByRole("heading", { name: "TEST3c" })).toBeVisible();
  await expect(inspector).toContainText("10,000 m (32,808.4 ft)");
  await expect(inspector).toContainText("48.85°N 2.35°E");

  const created = page.waitForRequest(
    (r) => r.method() === "POST" && r.url().endsWith("/watchlists"),
  );
  await inspector.getByRole("button", { name: "Watch" }).click();
  expect((await created).postDataJSON()).toEqual({
    name: "Watched",
    items: [{ kind: "aircraft", value: "3c6444", label: "TEST3c" }],
  });
  await expect(inspector.getByRole("button", { name: "Watching" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await inspector.getByRole("button", { name: "Close inspector" }).click();
  await expect(inspector).toHaveCount(0);
});

test("watched items are restored on reload", async ({ page, api }) => {
  api.watchlists = [
    {
      id: "w1",
      name: "Watched",
      items: [{ kind: "aircraft", value: "3c6444", label: null }],
      created_at: "t",
      updated_at: "t",
    },
  ];
  await page.goto("/");
  await expect(await layerRow(page, /Live flights/)).toHaveAttribute("aria-pressed", "true");
  expect(api.calls("GET", "/watchlists")).toHaveLength(1);
});
