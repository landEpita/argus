import type * as CesiumNS from "cesium";

declare global {
  interface Window {
    CESIUM_BASE_URL?: string;
    Cesium?: typeof CesiumNS;
  }
}

let loading: Promise<typeof CesiumNS> | null = null;

/**
 * Cesium's prebuilt library, served from /cesium (scripts/copy-cesium.mjs).
 * Loaded as a script on first use rather than bundled: it is large, and
 * Next's minifier rejects parts of its source.
 */
export function loadCesium(base = "/cesium/"): Promise<typeof CesiumNS> {
  if (window.Cesium) return Promise.resolve(window.Cesium);
  loading ??= new Promise((resolve, reject) => {
    window.CESIUM_BASE_URL = base;
    const script = document.createElement("script");
    script.src = `${base}Cesium.js`;
    script.async = true;
    script.onload = () =>
      window.Cesium ? resolve(window.Cesium) : reject(new Error("Cesium did not load"));
    script.onerror = () => {
      loading = null;
      reject(new Error("Cesium could not be downloaded"));
    };
    document.head.appendChild(script);
  });
  return loading;
}
