// AI contribution: 50% or more AI-generated
/**
 * Station-view Canvas consumer of Person 9's deterministic playback snapshots.
 * It uses fixture coordinates directly; it does not introduce a second mutable
 * simulation model, passenger positions or playback timer. Scaling the
 * fixture's fixed map box to the available viewport is handled by the pure
 * fitLayout() helper; this component only wires it to a ResizeObserver and a
 * canvas transform.
 */
import { useEffect, useRef, useState } from "react";
import { fitLayout } from "../lib/fitLayout";
import { getNetworkSnapshot } from "../lib/getNetworkSnapshot";
import { samplePassengers } from "../lib/samplePassengers";
import { usePlaybackStore } from "../store/usePlaybackStore";

interface ViewSize {
  width: number;
  height: number;
}

/** Marker budget for an individual connection; above this we sample and label the true count. */
const MAX_PASSENGER_MARKERS = 60;

/** Draw recorded map coordinates; seeking rebuilds rather than mutating sprites. */
export function StationCanvas() {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const data = usePlaybackStore((state) => state.data);
  const time = usePlaybackStore((state) => state.currentTime_s);
  const selected = usePlaybackStore((state) => state.selectedConnectionId);

  // Tracks the container's content box; falls back to the fixture's own
  // size (no scaling) when ResizeObserver is unavailable, e.g. in jsdom.
  const [viewSize, setViewSize] = useState<ViewSize | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    if (typeof ResizeObserver === "undefined") {
      // No observer available (e.g. jsdom): keep viewSize null so the draw
      // effect falls back to the fixture's own map size, unscaled.
      return;
    }

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const { width, height } = entry.contentRect;
      setViewSize({ width, height });
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, [data]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!context || !canvas || !data) return;

    const fallback = { width: data.map.width, height: data.map.height };
    const view = viewSize && viewSize.width > 0 && viewSize.height > 0 ? viewSize : fallback;
    const { scale, offsetX, offsetY } = fitLayout(data.map, view);

    // Crisp rendering on high-DPI screens: back the canvas with
    // devicePixelRatio-scaled pixels while keeping CSS size at the view box.
    const dpr = window.devicePixelRatio || 1;
    const pixelWidth = Math.max(1, Math.round(view.width * dpr));
    const pixelHeight = Math.max(1, Math.round(view.height * dpr));
    if (canvas.width !== pixelWidth) canvas.width = pixelWidth;
    if (canvas.height !== pixelHeight) canvas.height = pixelHeight;
    canvas.style.width = `${view.width}px`;
    canvas.style.height = `${view.height}px`;

    context.setTransform(1, 0, 0, 1, 0, 0);
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.scale(dpr, dpr);
    context.translate(offsetX, offsetY);
    context.scale(scale, scale);

    const snapshot = getNetworkSnapshot(data, time);

    // The selected corridor is derived from the same shared selection as the UI.
    const connection = data.connections.find((item) => item.id === selected);
    for (const corridor of data.corridors) {
      context.beginPath();
      corridor.path.forEach((point, index) => {
        if (index === 0) context.moveTo(point.x, point.y);
        else context.lineTo(point.x, point.y);
      });
      context.strokeStyle = corridor.id === connection?.corridor_id ? "#d8dbd5" : "#ecede9";
      context.lineWidth = 24;
      context.stroke();
    }

    // Platform positions and line colors come from the validated mapping adapter.
    context.font = "12px Arial";
    for (const platform of data.platforms) {
      context.fillStyle = platform.color;
      context.fillRect(platform.position.x - 135, platform.position.y - 10, 270, 20);
      context.fillStyle = "#16191d";
      context.fillText(`${platform.line_id.toUpperCase()} → ${platform.direction_label}`,
        platform.position.x - 135, platform.position.y + 30);
    }
    for (const train of snapshot.trains_at_platforms) {
      const platform = data.platforms.find((item) => item.platform_id === train.platform_id);
      if (!platform) continue;
      context.fillStyle = "#16191d";
      context.fillRect(platform.position.x - 100, platform.position.y - 8, 200, 16);
    }

    // No incremental passenger state: pause and backward seeking stay exact.
    const connectionPassengers = snapshot.passengers.filter(
      (passenger) => passenger.connection_id === selected,
    );
    const { sampled, trueCount } = samplePassengers(connectionPassengers, MAX_PASSENGER_MARKERS);
    for (const passenger of sampled) {
      context.beginPath();
      context.arc(passenger.position.x, passenger.position.y, 4, 0, 2 * Math.PI);
      context.fillStyle = passenger.phase === "boarding" ? "#007b78" : "#16191d";
      context.fill();
    }

    // The true count is always labeled, even when the drawn markers are a sample.
    // Drawn in screen space, after the fit transform is dropped: the label is
    // chrome, so it must not scale or drift with the map.
    if (selected) {
      context.setTransform(1, 0, 0, 1, 0, 0);
      context.scale(dpr, dpr);
      context.fillStyle = "#16191d";
      context.font = "12px Arial";
      const label = sampled.length < trueCount
        ? `Passengers: ${trueCount} (showing ${sampled.length})`
        : `Passengers: ${trueCount}`;
      context.fillText(label, 12, 20);
    }
  }, [data, time, selected, viewSize]);

  if (!data) return <p className="station-message">Choose a connection to load a mock run.</p>;
  return (
    <div ref={containerRef} className="station-canvas-wrap">
      <canvas ref={canvasRef} className="station-canvas"
        width={data.map.width} height={data.map.height}
        role="img" aria-label={`${data.interchange.name} at ${time.toFixed(1)} simulation seconds`}>
        Station schematic with platforms, transfer corridor, trains and passengers.
      </canvas>
    </div>
  );
}
