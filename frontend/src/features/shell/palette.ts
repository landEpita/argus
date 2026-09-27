export interface Command {
  id: string;
  label: string;
  /** Shown on the right: "Space", "Layer", "Region"… */
  kind: string;
  run(): void;
}

export const PALETTE_LIMIT = 9;

/**
 * Commands matching every word of the query; labels starting with the query
 * come first. The order of the input is kept otherwise, so callers decide
 * what matters most when the query is empty.
 */
export function filterCommands(
  commands: readonly Command[],
  query: string,
  limit = PALETTE_LIMIT,
): Command[] {
  const q = query.trim().toLowerCase();
  if (!q) return commands.slice(0, limit);
  const words = q.split(/\s+/);
  const matching = commands.filter((c) => {
    const text = `${c.label} ${c.kind}`.toLowerCase();
    return words.every((w) => text.includes(w));
  });
  const starts = matching.filter((c) => c.label.toLowerCase().startsWith(q));
  const rest = matching.filter((c) => !c.label.toLowerCase().startsWith(q));
  return [...starts, ...rest].slice(0, limit);
}
