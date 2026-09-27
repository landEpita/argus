import { isRasterLayer, type MapLayer } from "@/features/map/layers/types";

/** Shape as well as colour, so layers stay distinguishable without colour vision. */
export function swatchShape(layer: MapLayer): "arrow" | "dot" | "line" | "square" | "dash" {
  if (isRasterLayer(layer)) return "square";
  if (layer.id === "conflict") return "dash";
  if (layer.style.rotationProperty) return "arrow";
  if (layer.style.geometry === "line" || layer.style.geometry === "mixed") return "line";
  if (layer.style.geometry === "polygon") return "square";
  return "dot";
}

const ARROW = "polygon(50% 0, 100% 100%, 50% 72%, 0 100%)";

export function Swatch({ layer }: { layer: MapLayer }) {
  const shape = swatchShape(layer);
  const color = isRasterLayer(layer) ? "#9aa0ac" : layer.style.color;
  const style =
    shape === "arrow"
      ? { background: color, clipPath: ARROW, borderRadius: 0, width: 12, height: 12 }
      : shape === "dash"
        ? { color }
        : { background: color };
  const cls =
    shape === "dot"
      ? "swatch swatch-dot"
      : shape === "line"
        ? "swatch swatch-line"
        : shape === "dash"
          ? "swatch swatch-dash"
          : "swatch";
  return <span className={cls} style={style} aria-hidden="true" />;
}
