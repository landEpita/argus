/**
 * The live wall: which channels or webcams fill its tiles. Pure functions,
 * kept out of the components so they can be tested.
 */

export const WALL_SIZE = 4;

/** Put ``id`` in tile ``slot``; if it is already on the wall, the two tiles swap. */
export function place(wall: readonly string[], slot: number, id: string): string[] {
  const next = [...wall];
  const existing = next.indexOf(id);
  if (existing === slot) return next;
  if (existing >= 0) next[existing] = next[slot] ?? "";
  next[slot] = id;
  return next;
}

/** A saved wall, cleaned against the catalog; empty tiles are filled in catalog order. */
export function restore(saved: unknown, catalog: readonly string[]): string[] {
  const known = new Set(catalog);
  const kept = Array.isArray(saved)
    ? saved.filter((id): id is string => typeof id === "string" && known.has(id))
    : [];
  const unique = [...new Set(kept)].slice(0, WALL_SIZE);
  for (const id of catalog) {
    if (unique.length >= WALL_SIZE) break;
    if (!unique.includes(id)) unique.push(id);
  }
  return unique;
}

export function loadWall(key: string, catalog: readonly string[]): string[] {
  try {
    return restore(JSON.parse(localStorage.getItem(key) ?? "null"), catalog);
  } catch {
    return restore(null, catalog);
  }
}

export function saveWall(key: string, wall: readonly string[]): void {
  try {
    localStorage.setItem(key, JSON.stringify(wall));
  } catch {
    // Private mode or blocked storage: the wall simply is not remembered.
  }
}
