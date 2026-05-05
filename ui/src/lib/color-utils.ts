export const COLOR_HEX_MAP: Record<string, string> = {
  // Red tones
  red: "#ef4444",
  dark_red: "#991b1b",
  crimson: "#dc143c",
  scarlet: "#ff2400",
  maroon: "#800000",
  // Orange tones
  orange: "#f97316",
  dark_orange: "#c2410c",
  amber: "#f59e0b",
  peach: "#fcd34d",
  coral: "#fb923c",
  // Yellow tones
  yellow: "#eab308",
  gold: "#fbbf24",
  light_yellow: "#fef08a",
  mustard: "#a16207",
  khaki: "#ca8a04",
  // Green tones
  green: "#22c55e",
  dark_green: "#166534",
  light_green: "#86efac",
  olive: "#65a30d",
  lime: "#84cc16",
  forest_green: "#14532d",
  mint: "#6ee7b7",
  teal: "#14b8a6",
  // Blue tones
  blue: "#3b82f6",
  dark_blue: "#1e3a8a",
  light_blue: "#93c5fd",
  navy: "#1e3a5f",
  sky_blue: "#0ea5e9",
  royal_blue: "#4169e1",
  cobalt: "#0047ab",
  turquoise: "#40e0d0",
  // Purple tones
  purple: "#a855f7",
  dark_purple: "#6b21a8",
  light_purple: "#d8b4fe",
  violet: "#8b5cf6",
  lavender: "#a78bfa",
  magenta: "#d946ef",
  fuchsia: "#e879f9",
  plum: "#9333ea",
  // Brown tones
  brown: "#92400e",
  dark_brown: "#78350f",
  light_brown: "#d97706",
  tan: "#b45309",
  beige: "#f5f5dc",
  camel: "#c19a6b",
  // Pink tones
  pink: "#ec4899",
  light_pink: "#f9a8d4",
  hot_pink: "#f472b6",
  rose: "#fb7185",
  salmon: "#fa8072",
  // White/Grayscale tones
  white: "#ffffff",
  light_gray: "#d1d5db",
  silver: "#c0c0c0",
  // Black/Grayscale tones
  black: "#000000",
  dark_gray: "#374151",
  gray: "#6b7280"
};

export function getColorHex(colorName: string): string {
  if (!colorName) return "#cccccc";
  const normalized = colorName.toLowerCase().replace(/\s+/g, "_");
  return COLOR_HEX_MAP[normalized] || "#cccccc";
}

export function extractColors(response: any): string[] {
  const colors = new Set<string>();

  // From detected_attributes.color_name (primary color)
  if (response.detected_attributes?.color_name) {
    const color = response.detected_attributes.color_name.toLowerCase();
    if (color && color !== "unknown" && color !== "null" && color !== "undefined") {
      colors.add(color);
    }
  }

  // From all_items array - extract top 3 colors from detailed_colors
  if (response.all_items && response.all_items.length > 0) {
    response.all_items.forEach((item: any) => {
      // First try detailed_colors (top 3)
      if (item.detailed_colors && typeof item.detailed_colors === 'object') {
        const detailed = item.detailed_colors;
        const sortedColors = Object.entries(detailed)
          .sort(([, a], [, b]) => (b as number) - (a as number))
          .slice(0, 3)
          .map(([name]) => name.toLowerCase());

        sortedColors.forEach((color) => {
          if (color && color !== "unknown" && color !== "null" && color !== "undefined") {
            colors.add(color);
          }
        });
      }
      // Fallback to single color
      else if (item.color) {
        const color = item.color.toLowerCase();
        if (color && color !== "unknown" && color !== "null" && color !== "undefined") {
          colors.add(color);
        }
      }
    });
  }

  return Array.from(colors);
}
