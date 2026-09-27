import type { Aircraft } from "@/lib/api/types";

export function makeAircraft(overrides: Partial<Aircraft> = {}): Aircraft {
  return {
    icao24: "abc123",
    callsign: "AFR1234",
    registration: null,
    type_code: null,
    squawk: null,
    origin_country: "France",
    position: { lat: 48.85, lon: 2.35 },
    altitude_m: 10_000,
    velocity_ms: 230,
    heading_deg: 90,
    vertical_rate_ms: 0,
    on_ground: false,
    last_contact: "2026-09-27T12:00:00Z",
    source: "opensky",
    ...overrides,
  };
}
