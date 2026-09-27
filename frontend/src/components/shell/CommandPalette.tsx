"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { type Command, filterCommands } from "@/features/shell/palette";

interface Props {
  commands: readonly Command[];
  onClose(): void;
  /** When set, the typed text can be asked to the assistant. */
  onAsk?(question: string): void;
}

/** ⌘K: every space, region, layer, instrument and country, by typing. */
export function CommandPalette({ commands, onClose, onAsk }: Props) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const shown = useMemo(() => {
    const found = filterCommands(commands, query);
    const q = query.trim();
    if (!onAsk || !q) return found;
    return [
      ...found.slice(0, 8),
      { id: "ask", label: `Ask Argus: “${q}”`, kind: "Assistant", run: () => onAsk(q) },
    ];
  }, [commands, query, onAsk]);

  useEffect(() => {
    input.current?.focus();
  }, []);

  const run = (command: Command | undefined) => {
    if (!command) return;
    onClose();
    command.run();
  };

  return (
    <div className="palette-backdrop">
      <button
        type="button"
        className="palette-dismiss"
        aria-label="Close command palette"
        tabIndex={-1}
        onClick={onClose}
      />
      <div className="palette" role="dialog" aria-modal="true" aria-label="Command palette">
        <input
          ref={input}
          value={query}
          role="combobox"
          aria-expanded="true"
          aria-controls="palette-results"
          aria-activedescendant={shown[active] ? `palette-${active}` : undefined}
          placeholder="Search spaces, layers, regions, instruments, countries…"
          onChange={(e) => {
            setQuery(e.target.value);
            setActive(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") onClose();
            else if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((i) => Math.min(shown.length - 1, i + 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((i) => Math.max(0, i - 1));
            } else if (e.key === "Enter") run(shown[active]);
          }}
        />
        <div id="palette-results" role="listbox" aria-label="Commands" className="palette-list">
          {shown.map((c, i) => (
            <button
              key={c.id}
              id={`palette-${i}`}
              type="button"
              role="option"
              aria-selected={i === active}
              tabIndex={-1}
              onMouseEnter={() => setActive(i)}
              onClick={() => run(c)}
            >
              <span>{c.label}</span>
              <span className="kind">{c.kind}</span>
            </button>
          ))}
        </div>
        {shown.length === 0 && <p className="empty">Nothing matches “{query}”.</p>}
      </div>
    </div>
  );
}
