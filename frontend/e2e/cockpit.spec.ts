import { expect, test } from "./fixtures";

test("the command palette runs commands by typing", async ({ page }) => {
  await page.goto("/");
  await page.waitForFunction(() => window.__argusMap?.loaded());
  await page.keyboard.press("ControlOrMeta+k");
  const palette = page.getByRole("dialog", { name: "Command palette" });
  await expect(palette).toBeVisible();
  await page.keyboard.type("go to sources");
  await page.keyboard.press("Enter");
  await expect(palette).toHaveCount(0);
  await expect(page).toHaveURL(/#sources$/);

  await page.getByRole("button", { name: /Search or run a command/ }).click();
  await page.keyboard.type("ukraine");
  await expect(palette.getByRole("option").first()).toContainText("Ukraine");
  await page.keyboard.press("Escape");
  await expect(palette).toHaveCount(0);
});

test("planned features are shown as such, not faked", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: /Alerts/ })).toBeDisabled();
});

test("without a model, Ask Argus leads to the model settings", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Ask Argus" }).click();
  await expect(page).toHaveURL(/#sources$/);
  const card = page.getByRole("region", { name: "Assistant model" });
  await expect(card).toContainText("○ Off");
  await card.getByPlaceholder(/provider\/model/).fill("ollama/mistral");
  const saved = page.waitForRequest(
    (r) => r.method() === "PUT" && r.url().endsWith("/assistant/settings"),
  );
  await card.getByRole("button", { name: "Save" }).click();
  expect((await saved).postDataJSON()).toEqual({
    model: "ollama/mistral",
    api_base: null,
    embedding_model: null,
  });
  await expect(card).toContainText("saved in the app");
  // The key is sent only when typed, and never shown back.
  await card.getByLabel("API key").fill("sk-test-1234");
  const withKey = page.waitForRequest(
    (r) => r.method() === "PUT" && r.url().endsWith("/assistant/settings"),
  );
  await card.getByRole("button", { name: "Save" }).click();
  expect((await withKey).postDataJSON().api_key).toBe("sk-test-1234");
  await expect(card.getByLabel("API key")).toHaveValue("");
});

test("the assistant answers with its steps, sources and unbacked figures", async ({
  page,
  api,
}) => {
  api.set({ assistant: true });
  await page.goto("/");
  await page.getByRole("button", { name: "Ask Argus" }).click();
  const panel = page.getByRole("complementary", { name: "Assistant" });
  await panel.getByLabel("Question", { exact: true }).fill("How is oil doing?");
  const asked = page.waitForRequest((r) => r.url().endsWith("/assistant/ask"));
  await panel.getByRole("button", { name: "Ask", exact: true }).click();
  expect((await asked).postDataJSON()).toEqual({ question: "How is oil doing?", history: [] });
  await expect(panel).toContainText("Brent is down 8.59 %");
  await expect(panel.getByRole("list", { name: "Steps" })).toContainText("read quotes");
  await expect(panel).toContainText("No conclusion");
  await expect(panel).toContainText("do not appear in the data Argus read: 91");
  await expect(panel.getByText("GDELT (unverified)")).toHaveClass(/tag-unverified/);
  await expect(panel).toContainText("ollama/mistral · 4.2 s · 2 tool calls");

  // Follow-ups carry the conversation.
  await panel.getByLabel("Question", { exact: true }).fill("And gas?");
  const followUp = page.waitForRequest((r) => r.url().endsWith("/assistant/ask"));
  await panel.getByRole("button", { name: "Ask", exact: true }).click();
  expect((await followUp).postDataJSON().history).toHaveLength(2);
});

test("the palette can ask the assistant", async ({ page, api }) => {
  api.set({ assistant: true });
  await page.goto("/");
  await page.waitForFunction(() => window.__argusMap?.loaded());
  await page.keyboard.press("ControlOrMeta+k");
  await page.keyboard.type("red sea shipping");
  await expect(page.getByRole("option", { name: /Ask Argus: “red sea shipping”/ })).toBeVisible();
  await page.getByRole("option", { name: /Ask Argus/ }).click();
  await expect(page.getByRole("complementary", { name: "Assistant" })).toContainText(
    "red sea shipping",
  );
});

test("sources list health, missing keys and where to set them", async ({ page, api }) => {
  api.set({
    health: {
      status: "failing",
      version: "t",
      sources: [
        {
          source: "usgs",
          status: "ok",
          last_success_age_s: 40,
          last_error: null,
          consecutive_failures: 0,
        },
        {
          source: "polymarket",
          status: "failing",
          last_success_age_s: null,
          last_error: "DNS",
          consecutive_failures: 4,
        },
      ],
    },
  });
  await page.goto("/#sources");
  await expect(page.getByRole("status")).toHaveText(/Degraded/);
  const main = page.getByRole("main", { name: "Sources" });
  await expect(main.getByRole("row", { name: /Polymarket/ })).toContainText("■ Down");
  await expect(main.getByRole("row", { name: /AISStream/ })).toContainText("Needs key");
  await expect(main.getByRole("row", { name: /USGS/ })).toContainText("● OK");
  await expect(main).toContainText("ARGUS_AISSTREAM_API_KEY");
});

test("watchlists can be created and filled with validated items", async ({ page, api }) => {
  await page.goto("/#watch");
  const main = page.getByRole("main", { name: "Watch" });
  await main.getByLabel("New list name").fill("Gulf tankers");
  await main.getByRole("button", { name: "Create list" }).click();
  await expect(main.getByRole("heading", { name: "Gulf tankers" })).toBeVisible();

  await main.getByRole("button", { name: "Ship" }).click();
  await main.getByLabel("Value").fill("1234");
  await expect(main.getByText("An MMSI has exactly 9 digits.")).toBeVisible();

  await main.getByRole("button", { name: "Ticker" }).click();
  await main.getByLabel("Value").fill("bz=f");
  await expect(main.getByText("Will be saved as BZ=F")).toBeVisible();
  const saved = page.waitForRequest(
    (r) => r.method() === "PUT" && r.url().includes("/watchlists/"),
  );
  await main.getByRole("button", { name: "Add", exact: true }).click();
  expect((await saved).postDataJSON().items).toEqual([
    { kind: "ticker", value: "BZ=F", label: null },
  ]);
  await expect(main.getByRole("row", { name: /BZ=F/ })).toContainText("97.44 USD/bbl");
  expect(api.watchlists[0]?.items).toHaveLength(1);
});

test("an answer can put what it read on the map", async ({ page, api }) => {
  api.set({ assistant: true });
  await page.goto("/");
  await page.waitForFunction(() => window.__argusMap?.loaded());
  await page.getByRole("button", { name: "Ask Argus" }).click();
  const panel = page.getByRole("complementary", { name: "Assistant" });
  await panel.getByLabel("Question", { exact: true }).fill("Red Sea?");
  await panel.getByRole("button", { name: "Ask", exact: true }).click();
  await panel.getByRole("button", { name: /Show on map · conflict/ }).click();
  await page.waitForFunction(() => {
    const c = window.__argusMap?.getCenter();
    return c !== undefined && Math.abs(c.lat - 15) < 0.5 && Math.abs(c.lng - 42) < 0.5;
  });
  await expect(page.getByTitle("Hide Reported violence (6 h)")).toBeVisible();
});

test("a prediction market is checked against Argus data", async ({ page, api }) => {
  api.set({ assistant: true, predictionOpen: true });
  await page.goto("/#markets");
  const card = page.getByRole("region", { name: "Prediction markets" });
  await expect(card).toContainText("Shipping through Hormuz disrupted");
  await card.getByRole("button", { name: /Analyse with Argus data/ }).click();
  const analysis = card.getByLabel("Analysis");
  await expect(analysis).toContainText("No conclusion");
  await expect(analysis).toContainText("the market price is not used as evidence");
});

test("settings show usage, the embedding model and how to connect over MCP", async ({
  page,
  api,
}) => {
  api.set({ assistant: true });
  await page.goto("/#sources");
  const card = page.getByRole("region", { name: "Assistant model" });
  await expect(card).toContainText("12 model calls");
  await expect(card).toContainText("$0.0123 estimated");
  await card.getByLabel(/Embedding model/).fill("ollama/nomic-embed-text");
  const saved = page.waitForRequest(
    (r) => r.method() === "PUT" && r.url().endsWith("/assistant/settings"),
  );
  await card.getByRole("button", { name: "Save" }).click();
  expect((await saved).postDataJSON().embedding_model).toBe("ollama/nomic-embed-text");
  await card.getByText(/Use Argus from Claude Desktop or Claude Code/).click();
  await expect(card).toContainText(
    "claude mcp add --transport http argus http://localhost:8000/mcp",
  );
});
