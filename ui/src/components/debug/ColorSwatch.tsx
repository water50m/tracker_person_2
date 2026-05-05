"use client";

import { getColorHex } from "@/lib/color-utils";

interface ColorSwatchProps {
  colorName: string;
  hex?: string;
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
  percentage?: number;
}

export function ColorSwatch({
  colorName,
  hex,
  size = "md",
  showLabel = true,
  percentage,
}: ColorSwatchProps) {
  const colorHex = hex || getColorHex(colorName);

  const sizeClasses = {
    sm: "w-6 h-6",
    md: "w-10 h-10",
    lg: "w-14 h-14",
  };

  const formattedName = colorName
    ? colorName.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
    : "Unknown";
  const colorPercentage = percentage ? (percentage ).toFixed(1) : "0";
  return (
    <div className="flex items-center gap-3">
      <div
        className={`${sizeClasses[size]} rounded-md border-2 border-gray-300 shadow-sm flex-shrink-0`}
        style={{ backgroundColor: colorHex }}
        title={colorName}
      />
      {showLabel && (
        <div className="text-sm">
          <div className="font-medium mr-2" style={{ color: colorHex }}>{colorPercentage}% </div>
        </div>
      )}
    </div>
  );
}
