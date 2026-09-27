"use client";

import { useEffect, useMemo, useState } from "react";
import type { CountryDirectory } from "@/features/intel/countries";
import { PollingResource } from "@/features/intel/resource";
import { useResource } from "@/features/intel/useResource";
import type { ApiClient } from "@/lib/api/client";
import type { NewsCategory, StoryCollection } from "@/lib/api/types";
import { StoryItem } from "./StoryItem";

const CATEGORIES: { id: NewsCategory | null; label: string }[] = [
  { id: null, label: "All" },
  { id: "world", label: "World" },
  { id: "defense", label: "Defense" },
  { id: "cyber", label: "Cyber" },
  { id: "regional", label: "Regional" },
];

interface Props {
  api: ApiClient;
  countries: CountryDirectory;
  onFocusCountry(iso2: string): void;
}

export function NewsPanel({ api, countries, onFocusCountry }: Props) {
  const [category, setCategory] = useState<NewsCategory | null>(null);
  const [query, setQuery] = useState("");
  const resource = useMemo(
    () =>
      new PollingResource<StoryCollection>((signal) => api.news({ limit: 150 }, signal), 300_000),
    [api],
  );
  useEffect(() => {
    const q = query.trim() || undefined;
    resource.setLoader((signal) =>
      api.news({ limit: 150, category: category ?? undefined, q }, signal),
    );
  }, [api, resource, category, query]);
  const { data, error, loading } = useResource(resource);

  const failing = data?.sources.filter((s) => s.error) ?? [];
  return (
    <div className="intel-panel">
      <div className="intel-toolbar">
        <fieldset className="segmented">
          <legend className="sr-only">Category</legend>
          {CATEGORIES.map((c) => (
            <button
              key={c.label}
              type="button"
              aria-pressed={category === c.id}
              onClick={() => setCategory(c.id)}
            >
              {c.label}
            </button>
          ))}
        </fieldset>
        <input
          type="search"
          placeholder="Filter headlines…"
          aria-label="Filter headlines"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      {error != null && data && (
        <p className="notice notice-warn">Could not refresh; showing earlier stories.</p>
      )}
      {error != null && !data && (
        <p className="notice notice-error">News is unavailable right now.</p>
      )}
      {!data && loading && <p className="notice">Loading stories…</p>}
      {data && data.items.length === 0 && <p className="notice">No stories match.</p>}

      <ol className="story-list">
        {data?.items.map((story) => (
          <StoryItem
            key={story.id}
            story={story}
            countries={countries}
            onFocusCountry={onFocusCountry}
          />
        ))}
      </ol>

      {data && (
        <footer
          className="intel-footer"
          title={failing.map((s) => `${s.source.name}: ${s.error}`).join("\n")}
        >
          {data.sources.length - failing.length}/{data.sources.length} sources answering
          {data.truncated ? " · showing the most recent" : ""}
        </footer>
      )}
    </div>
  );
}
