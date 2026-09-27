"use client";

import { Segmented } from "@/components/shell/Segmented";
import { REGIONS, type Region } from "@/features/map/regions";
import type { Projection } from "@/features/map/renderer";

interface Props {
  region: string | null;
  projection: Projection;
  onRegion(region: Region): void;
  onProjection(projection: Projection): void;
}

export function RegionBar({ region, projection, onRegion, onProjection }: Props) {
  return (
    <div className="regionbar">
      <Segmented label="Regions">
        {REGIONS.map((r) => (
          <button
            key={r.id}
            type="button"
            aria-pressed={region === r.id}
            onClick={() => onRegion(r)}
          >
            {r.label}
          </button>
        ))}
      </Segmented>
      <Segmented label="Projection">
        <button
          type="button"
          aria-pressed={projection === "mercator"}
          onClick={() => onProjection("mercator")}
        >
          2D
        </button>
        <button
          type="button"
          aria-pressed={projection === "globe"}
          onClick={() => onProjection("globe")}
        >
          3D
        </button>
        <button
          type="button"
          aria-pressed={projection === "realistic"}
          title="Satellite globe with aircraft at their altitude, and the cockpit view"
          onClick={() => onProjection("realistic")}
        >
          Globe
        </button>
      </Segmented>
    </div>
  );
}
