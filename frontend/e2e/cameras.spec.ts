import { clickLonLat, DEFAULT_PREFERENCES, expect, test } from "./fixtures";

const PIXEL = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=",
  "base64",
);

test("an open camera shows its facing and its latest frame", async ({ page, api }) => {
  await page.route("https://www.drivebc.ca/**", (route) =>
    route.fulfill({ body: PIXEL, contentType: "image/png" }),
  );
  api.set({
    cameras: [
      {
        id: "drivebc:900",
        network: "drivebc",
        name: "Whiskers Point - S",
        position: { lat: 54.9, lon: -122.93 },
        heading_deg: 180,
        feed: "image",
        url: "https://www.drivebc.ca/images/900.jpg",
        still_url: "https://www.drivebc.ca/images/900.jpg",
        description: "Highway 97, looking south.",
        source: "drivebc",
      },
    ],
    preferences: {
      ...DEFAULT_PREFERENCES,
      enabled_layers: ["open-cameras"],
      viewport: { center: { lat: 54.9, lon: -122.93 }, zoom: 14 },
    },
  });
  await page.goto("/");
  await expect(page.getByTitle("Hide Open cameras")).toContainText("1"); // the cone is not counted
  await clickLonLat(page, -122.93, 54.9);

  const inspector = page.getByRole("complementary", { name: "Inspector" });
  await expect(inspector.getByRole("heading", { name: "Whiskers Point - S" })).toBeVisible();
  await expect(inspector).toContainText("S (180°)");
  await expect(
    inspector.getByRole("img", { name: "Latest frame: Whiskers Point - S" }),
  ).toBeVisible();
  await expect(inspector).toContainText("DriveBC");
});
