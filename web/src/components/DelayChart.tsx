// AI contribution: 50% or more AI-generated
/**
 * Passenger delay over time for one simulator run.
 *
 * Recharts provides the line, axes and hover layer; hold and adaptive-switch
 * reference lines reuse the API records so markers cannot drift from playback.
 */
import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  delayChartPoints,
  formatElapsedTime,
  holdEventMarkers,
  holdsForDelayBucket,
} from "../lib/delaySeries";
import { usePlaybackStore } from "../store/usePlaybackStore";
import type { HoldEvent } from "../types/stationView";
import "./delay-chart.css";

interface DelayTooltipProps {
  active?: boolean;
  payload?: readonly { payload?: { time_s: number; average_passenger_delay_s: number; passenger_count: number } }[];
  bucket_s: number;
  holdEvents: readonly HoldEvent[];
}

/** Explain the exact bucket time, passenger average and sample count on hover. */
function DelayTooltip({
  active, payload, bucket_s, holdEvents,
}: Readonly<DelayTooltipProps>) {
  if (!active || payload?.length !== 1) return null;
  const point = payload[0].payload;
  if (!point) return null;
  const holds = holdsForDelayBucket(holdEvents, point.time_s, point.time_s + bucket_s);
  return (
    <div className="delay-tooltip" role="status">
      <strong>{formatElapsedTime(point.time_s)}</strong>
      <span>{point.average_passenger_delay_s.toFixed(1)} s / passenger</span>
      <span>{point.passenger_count} passengers</span>
      {holds.slice(0, 3).map((event) => (
        <span key={`${event.time_s}-${event.train_id}`}>
          Hold at {formatElapsedTime(event.time_s)} · {event.train_id} ·
          {" "}{event.applied_s.toFixed(1)} s
        </span>
      ))}
      {holds.length > 3 && <span>{holds.length - 3} more holds in this bucket</span>}
    </div>
  );
}

/** Render the chart only for simulator responses that contain time-series data. */
export function DelayChart() {
  const data = usePlaybackStore((state) => state.data);
  const timeSeries = data?.time_series;
  const points = useMemo(
    () => timeSeries ? delayChartPoints(timeSeries) : [],
    [timeSeries],
  );
  const holdMarkers = useMemo(
    () => timeSeries ? holdEventMarkers(timeSeries.hold_events) : [],
    [timeSeries],
  );
  if (!timeSeries || points.length === 0) return null;

  return (
    <section className="panel delay-chart" aria-label="Passenger delay over time">
      <div className="delay-chart-heading">
        <h2>Passenger delay over time</h2>
        <span>Average waiting delay per passenger · 5-minute buckets</span>
      </div>
      <div className="delay-chart-canvas">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 12, right: 18, bottom: 8, left: 4 }}>
            <CartesianGrid stroke="#e4e6e1" strokeDasharray="3 3" />
            <XAxis
              dataKey="time_s"
              type="number"
              domain={[timeSeries.start_s, timeSeries.end_s]}
              tickFormatter={(value: number) => `${Math.floor(value / 60)}m`}
              allowDecimals={false}
              tick={{ fill: "#5b6168", fontSize: 12 }}
            />
            <YAxis
              width={58}
              tickFormatter={(value: number) => `${value}s`}
              tick={{ fill: "#5b6168", fontSize: 12 }}
            />
            <Tooltip
              content={<DelayTooltip
                bucket_s={timeSeries.bucket_s}
                holdEvents={timeSeries.hold_events}
              />}
              cursor={{ stroke: "#16191d", strokeDasharray: "3 3" }}
            />
            {holdMarkers.map((event) => (
              <ReferenceLine
                key={`${event.time_s}-${event.train_id}`}
                x={event.time_s}
                stroke="#b42318"
                strokeWidth={2}
                label={{ value: "Hold", position: "insideTop", fill: "#b42318", fontSize: 11 }}
              />
            ))}
            {(data?.mode_switches ?? []).map((event) => (
              <ReferenceLine
                key={`${event.time_s}-${event.train_id}`}
                x={event.time_s}
                stroke="#7a5af8"
                strokeDasharray="5 4"
                label={{ value: "Mode", position: "insideBottom", fill: "#6a4ee0", fontSize: 11 }}
              />
            ))}
            <Line
              type="monotone"
              dataKey="average_passenger_delay_s"
              name="Average passenger delay"
              stroke="#16191d"
              strokeWidth={2.5}
              dot={{ r: 3, fill: "#fff", stroke: "#16191d", strokeWidth: 2 }}
              activeDot={{ r: 5, fill: "#16191d" }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
