import { expect, test } from "./fixtures";

test("the live wall plays four channels and a pick replaces the active tile", async ({ page }) => {
  await page.route("https://www.youtube-nocookie.com/**", (route) =>
    route.fulfill({ body: "<html></html>", contentType: "text/html" }),
  );
  await page.goto("/#live");
  const wall = page.getByRole("region", { name: "Players" });
  await expect(wall.locator("iframe")).toHaveCount(4);
  await expect(wall.getByRole("article", { name: "BLOOMBERG" })).toBeVisible();

  await page
    .getByRole("region", { name: "Channels" })
    .getByRole("button", { name: /NHK-WORLD/ })
    .click();
  await expect(wall.getByRole("article", { name: "NHK-WORLD" })).toBeVisible();
  await expect(wall.getByRole("article", { name: "BLOOMBERG" })).toHaveCount(0);

  await page.getByRole("tab", { name: "Webcams" }).click();
  await expect(page).toHaveURL(/#live\/webcams$/);
});
