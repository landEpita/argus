import type { CountryInfo } from "@/lib/api/types";

/** ISO2 -> country, for chip labels and fly-to. */
export class CountryDirectory {
  private readonly byCode: Map<string, CountryInfo>;

  constructor(countries: readonly CountryInfo[]) {
    this.byCode = new Map(countries.map((c) => [c.iso2, c]));
  }

  get(iso2: string): CountryInfo | undefined {
    return this.byCode.get(iso2.toUpperCase());
  }

  /** Every country, by name. */
  all(): CountryInfo[] {
    return [...this.byCode.values()].sort((a, b) => a.name.localeCompare(b.name));
  }

  name(iso2: string): string {
    return this.get(iso2)?.name ?? iso2;
  }
}

export const EMPTY_DIRECTORY = new CountryDirectory([]);
