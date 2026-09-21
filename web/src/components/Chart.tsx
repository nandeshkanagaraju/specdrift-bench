import type { ReactNode } from "react";
import { useTheme } from "../lib/theme";

/** Shared chart chrome so every chart in the app reads the same. */
export function useChartColors() {
  const { theme } = useTheme();
  return {
    grid: theme === "light" ? "#e6e9ef" : "#232833",
    axis: theme === "light" ? "#5b6474" : "#8a92a6",
    tooltipBg: theme === "light" ? "#ffffff" : "#181c25",
    series: ["#2dd4bf", "#fb7185", "#818cf8"],
  };
}

export function ChartTooltipStyle() {
  const colors = useChartColors();
  return {
    contentStyle: {
      background: colors.tooltipBg,
      border: `1px solid ${colors.grid}`,
      borderRadius: 10,
      fontSize: 12,
    },
    labelStyle: { color: colors.axis, fontSize: 11 },
    cursor: { fill: "rgba(138,146,166,0.08)" },
  };
}

export function ChartFrame({ children, height = 260 }: { children: ReactNode; height?: number }) {
  return <div style={{ width: "100%", height }}>{children}</div>;
}
