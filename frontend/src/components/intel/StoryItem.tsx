"use client";

import type { CountryDirectory } from "@/features/intel/countries";
import { coverageLabel, describeSource } from "@/features/intel/present";
import type { Story } from "@/lib/api/types";
import { formatRelative, formatUtc } from "@/lib/time/relative";

interface Props {
  story: Story;
  countries: CountryDirectory;
  onFocusCountry(iso2: string): void;
}

export function StoryItem({ story, countries, onFocusCountry }: Props) {
  return (
    <li className="story">
      <a href={story.url} target="_blank" rel="noopener noreferrer" className="story-title">
        {story.title}
      </a>
      <div className="story-meta">
        <time dateTime={story.last_updated} title={formatUtc(story.last_updated)}>
          {formatRelative(story.last_updated)}
        </time>
        <span
          className={`coverage coverage-${Math.min(story.sources.length, 3)}`}
          title={story.sources.map(describeSource).join("\n")}
        >
          {coverageLabel(story)}: {story.sources.map((s) => s.name).join(", ")}
        </span>
        {story.state_media_only && (
          <span className="tag tag-warn" title="Only state-controlled outlets report this">
            State media only
          </span>
        )}
      </div>
      {story.countries.length > 0 && (
        <ul className="chips" aria-label="Countries mentioned (detected automatically)">
          {story.countries.slice(0, 5).map((code) => (
            <li key={code}>
              <button
                type="button"
                className="chip chip-small"
                title={`Show ${countries.name(code)} on the map`}
                onClick={() => onFocusCountry(code)}
              >
                {countries.name(code)}
              </button>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
