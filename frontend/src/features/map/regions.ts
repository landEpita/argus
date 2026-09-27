/** Camera presets of the region bar: [west, south, east, north]. */
export interface Region {
  id: string;
  label: string;
  bounds: readonly [number, number, number, number];
}

export const REGIONS: readonly Region[] = [
  { id: "world", label: "World", bounds: [-170, -58, 170, 75] },
  { id: "europe", label: "Europe", bounds: [-12, 35, 40, 70] },
  { id: "middle-east", label: "Middle East", bounds: [25, 12, 63, 42] },
  { id: "ukraine", label: "Ukraine", bounds: [22, 44, 41, 53] },
  { id: "taiwan", label: "Taiwan", bounds: [116, 20, 126, 27] },
  { id: "red-sea", label: "Red Sea", bounds: [31, 10, 46, 30] },
];
