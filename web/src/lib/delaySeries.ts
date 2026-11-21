// AI contribution: 50% or more AI-generated
/** Derive chart points and de-cluttered event markers for the delay-over-time view. */

import type { HoldEvent, TimeSeriesData } from "../types/stationView";

/** One chart-ready bucket with a local axis label. */
export interface DelayChartPoint {
  time_s: number;
  label: string;
  average_passenger_delay_s: number;
  passenger_count: number;
}

/** Format simulation seconds as whole elapsed minutes for axis labels. */
export function formatElapsedMinutes(time_s: number): string {
  return `${Math.floor(time_s / 60)}m`;
}

/** Convert API buckets to Recharts points; missing buckets cannot hide horizon gaps. */
export function delayChartPoints(timeSeries: TimeSeriesData): DelayChartPoint[] {
  return timeSeries.buckets.map((bucket) => ({
    time_s: bucket.start_s,
    label: formatElapsedMinutes(bucket.start_s),
    average_passenger_delay_s: bucket.average_passenger_delay_s,
    passenger_count: bucket.passenger_count,
  }));
}

/**
 * Merge hold markers closer than 30 seconds and cap visual clutter.
 * Exact nearby holds remain visible through the hover readout and hold tooltip.
 */
export function holdEventMarkers(holdEvents: readonly HoldEvent[]): HoldEvent[] {
  const kept: HoldEvent[] = [];
  for (const event of [...holdEvents].sort((a, b) => a.time_s - b.time_s)) {
    if (kept.some((existing) => Math.abs(existing.time_s - event.time_s) < 30)) continue;
    kept.push(event);
  }
  if (kept.length <= 12) return kept;
  const stride = (kept.length - 1) / 11;
  return Array.from({ length: 12 }, (_, index) => kept[Math.round(index * stride)]);
}
