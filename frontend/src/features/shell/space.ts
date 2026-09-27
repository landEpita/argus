/** The cockpit's top-level spaces. The URL hash carries the current one (#markets). */
export const SPACES = ["map", "live", "watch", "markets", "countries", "sources"] as const;
export type Space = (typeof SPACES)[number];

export const SPACE_LABELS: Record<Space, string> = {
  map: "Map",
  live: "Live",
  watch: "Watch",
  markets: "Markets",
  countries: "Countries",
  sources: "Sources",
};

const isSpace = (value: string): value is Space => (SPACES as readonly string[]).includes(value);

/** "#markets", "#/markets" and "#markets/BZ=F" all open Markets; anything else opens the map. */
export function parseHash(hash: string): { space: Space; param: string | null } {
  const [head = "", ...rest] = hash.replace(/^#\/?/, "").split("/");
  if (!isSpace(head)) return { space: "map", param: null };
  const param = rest.length ? decodeURIComponent(rest.join("/")) : null;
  return { space: head, param: param || null };
}

export function hashFor(space: Space, param: string | null = null): string {
  if (space === "map" && !param) return "";
  return `#${space}${param ? `/${encodeURIComponent(param)}` : ""}`;
}
