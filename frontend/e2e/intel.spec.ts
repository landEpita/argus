import { DEFAULT_PREFERENCES, expect, test } from "./fixtures";

test("news stories show coverage, state-media flags and source health", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "News" }).click();
  const dock = page.getByRole("complementary", { name: "Right now" });
  await expect(dock.getByRole("link", { name: /Strait of Hormuz/ })).toHaveAttribute(
    "rel",
    "noopener noreferrer",
  );
  await expect(dock).toContainText("2 sources: BBC News, NPR");
  await expect(dock.locator(".story", { hasText: "Kremlin" })).toContainText("State media only");
  await expect(dock).toContainText("1/2 sources answering");
});

test("a country chip flies the map there", async ({ page }) => {
  await page.goto("/");
  await page.waitForFunction(() => window.__argusMap?.loaded());
  await page.getByRole("tab", { name: "News" }).click();
  await page.getByRole("button", { name: "Iran", exact: true }).click();
  await page.waitForFunction(() => {
    const c = window.__argusMap?.getCenter();
    return c !== undefined && Math.abs(c.lng - 53) < 1 && Math.abs(c.lat - 32) < 1;
  });
});

test("a Telegram channel can be added; posts are marked unverified; the choice is saved", async ({
  page,
  api,
}) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "Telegram" }).click();
  const input = page.getByLabel("Add a Telegram channel");

  await input.fill("not a channel!");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByText("Not a public channel name.")).toBeVisible();

  const saved = page.waitForRequest(
    (r) => r.method() === "PUT" && r.url().endsWith("/preferences"),
  );
  await input.fill("https://t.me/s/OsintDefender");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  expect((await saved).postDataJSON().telegram_channels).toEqual(["osintdefender"]);

  const post = page.locator(".story", { hasText: "Explosions reported near Kherson" });
  await expect(post).toContainText("Unverified");
  await expect(post.getByRole("link", { name: "Open on Telegram" })).toHaveAttribute(
    "href",
    "https://t.me/osintdefender/42",
  );
  expect(api.calls("GET", "/intel/telegram")[0]?.url()).toContain("channels=osintdefender");
});

test("saved channels load without asking", async ({ page, api }) => {
  api.set({ preferences: { ...DEFAULT_PREFERENCES, telegram_channels: ["wartranslated"] } });
  await page.goto("/");
  await page.getByRole("tab", { name: "Telegram" }).click();
  await expect(page.getByText("@wartranslated")).toBeVisible();
});

test("the cyber tab lists exploited vulnerabilities", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "Cyber" }).click();
  await expect(
    page.getByRole("link", { name: /CVE-2026-65660 — Microsoft Exchange/ }),
  ).toBeVisible();
  await expect(page.getByText("Used by ransomware")).toBeVisible();
});

test("the panel can be closed and reopened", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Hide panel" }).click();
  await expect(page.getByRole("complementary", { name: "Right now" })).toHaveCount(0);
  await page.getByRole("button", { name: "Right now ›" }).click();
  await expect(page.getByRole("complementary", { name: "Right now" })).toBeVisible();
});
