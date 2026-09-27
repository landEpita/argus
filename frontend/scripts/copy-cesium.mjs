// Cesium loads its web workers, assets and widget CSS at run time from
// CESIUM_BASE_URL; copy them, and the library, next to the app so the globe
// needs no CDN.
import { cpSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const source = join(root, "node_modules", "cesium", "Build", "Cesium");
const target = join(root, "public", "cesium");
if (!existsSync(source)) {
  console.error("cesium is not installed; run npm ci first");
  process.exit(1);
}
mkdirSync(target, { recursive: true });
for (const dir of ["Workers", "ThirdParty", "Assets", "Widgets"]) {
  cpSync(join(source, dir), join(target, dir), { recursive: true });
}
// The prebuilt library itself: loaded as a script, not bundled (Next's
// minifier rejects parts of Cesium's source).
cpSync(join(source, "Cesium.js"), join(target, "Cesium.js"));
