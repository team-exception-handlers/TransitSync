// AI contribution: 50% or more AI-generated
/**
 * Station-view Canvas consumer of Person 9's deterministic playback snapshots.
 * It uses fixture coordinates directly; it does not introduce a second mutable
 * simulation model, passenger positions or playback timer. Scaling the
 * fixture's fixed map box to the available viewport is handled by the pure
 * fitLayout() helper; this component only wires it to a ResizeObserver and a
 * canvas transform. Clicking a marker follows that passenger (#237); the pick
 * lives in the playback store so other views can highlight the same person.
 */
import { type MouseEvent, useEffect, useRef, useState } from "react";
import { fitLayout } from "../lib/fitLayout";
import { getNetworkSnapshot } from "../lib/getNetworkSnapshot";
import { pickPassenger } from "../lib/pickPassenger";
import { samplePassengers } from "../lib/samplePassengers";
import { usePlaybackStore } from "../store/usePlaybackStore";
import type {
  PassengerPosition,
  Platform,
  Point,
  TrainAtPlatform,
  TransferCorridor,
} from "../types/stationView";

interface ViewSize {
  width: number;
  height: number;
}

/** Marker budget for an individual connection; above this we sample and label the true count. */
const MAX_PASSENGER_MARKERS = 60;

/**
 * Draws one passenger marker. Each non-walking phase uses a distinct shape
 * and outline, not just a different fill color, so the state reads even
 * without color vision (see connection-selector.tsx for the same approach).
 */
function drawPassengerMarker(
  context: CanvasRenderingContext2D,
  position: Point,
  phase: PassengerPosition["phase"],
) {
  const { x, y } = position;

  switch (phase) {
    case "queued": {
      // Queued: an outlined square (standing in a line), no fill.
      context.strokeStyle = "#16191d";
      context.lineWidth = 1.5;
      context.strokeRect(x - 4, y - 4, 8, 8);
      return;
    }
    case "waiting": {
      // Waiting on the platform: a filled circle with a visible ring outline.
      context.beginPath();
      context.arc(x, y, 4, 0, 2 * Math.PI);
      context.fillStyle = "#16191d";
      context.fill();
      context.strokeStyle = "#ffffff";
      context.lineWidth = 1.5;
      context.stroke();
      return;
    }
    case "boarding": {
      // Boarding: a filled triangle, distinct in shape as well as color.
      context.beginPath();
      context.moveTo(x, y - 5);
      context.lineTo(x + 5, y + 4);
      context.lineTo(x - 5, y + 4);
      context.closePath();
      context.fillStyle = "#007b78";
      context.fill();
      return;
    }
    case "missed": {
      // Missed the connection: an outlined circle with a cross through it.
      context.beginPath();
      context.arc(x, y, 4, 0, 2 * Math.PI);
      context.strokeStyle = "#b3261e";
      context.lineWidth = 1.5;
      context.stroke();
      context.beginPath();
      context.moveTo(x - 3, y - 3);
      context.lineTo(x + 3, y + 3);
      context.moveTo(x - 3, y + 3);
      context.lineTo(x + 3, y - 3);
      context.stroke();
      return;
    }
    default: {
      // Walking: a simple filled circle.
      context.beginPath();
      context.arc(x, y, 4, 0, 2 * Math.PI);
      context.fillStyle = "#16191d";
      context.fill();
      return;
    }
  }
}

/** Ring around the followed passenger (#237), drawn last so no other marker covers it. */
function drawSelectionRing(context: CanvasRenderingContext2D, position: Point) {
  context.beginPath();
  context.arc(position.x, position.y, 8, 0, 2 * Math.PI);
  context.strokeStyle = "#1a5fb4";
  context.lineWidth = 2;
  context.stroke();
}

/**
 * The markers drawn for the selected connection. Drawing and click picking
 * share this, so a click can only land on a passenger that is on screen.
 */
function connectionSample(
  passengers: readonly PassengerPosition[],
  connectionId: string | null,
  followedId: string | null,
) {
  const onConnection = passengers.filter((passenger) => passenger.connection_id === connectionId);
  return samplePassengers(onConnection, MAX_PASSENGER_MARKERS, followedId);
}

/**
 * Use the observed view box when it has a real size; otherwise fall back to
 * the fixture's own map size, which draws the layout unscaled.
 */
function chooseView(viewSize: ViewSize | null, map: ViewSize): ViewSize {
  if (viewSize && viewSize.width > 0 && viewSize.height > 0) return viewSize;
  return { width: map.width, height: map.height };
}

/**
 * Crisp rendering on high-DPI screens: back the canvas with
 * devicePixelRatio-scaled pixels while keeping its CSS size at the view box.
 * The pixel size is only reassigned when it changes, because assigning it
 * clears the canvas.
 */
function sizeCanvas(canvas: HTMLCanvasElement, view: ViewSize, dpr: number) {
  const pixelWidth = Math.max(1, Math.round(view.width * dpr));
  const pixelHeight = Math.max(1, Math.round(view.height * dpr));
  if (canvas.width !== pixelWidth) canvas.width = pixelWidth;
  if (canvas.height !== pixelHeight) canvas.height = pixelHeight;
  canvas.style.width = `${view.width}px`;
  canvas.style.height = `${view.height}px`;
}

/** Draw every transfer corridor, shading the selected connection's corridor darker. */
function drawCorridors(
  context: CanvasRenderingContext2D,
  corridors: readonly TransferCorridor[],
  highlightedId: string | undefined,
) {
  for (const corridor of corridors) {
    context.beginPath();
    corridor.path.forEach((point, index) => {
      if (index === 0) context.moveTo(point.x, point.y);
      else context.lineTo(point.x, point.y);
    });
    context.strokeStyle = corridor.id === highlightedId ? "#d8dbd5" : "#ecede9";
    context.lineWidth = 24;
    context.stroke();
  }
}

/** Platform positions and line colors come from the validated mapping adapter. */
function drawPlatforms(context: CanvasRenderingContext2D, platforms: readonly Platform[]) {
  context.font = "12px Arial";
  for (const platform of platforms) {
    context.fillStyle = platform.color;
    context.fillRect(platform.position.x - 135, platform.position.y - 10, 270, 20);
    context.fillStyle = "#16191d";
    context.fillText(`${platform.line_id.toUpperCase()} → ${platform.direction_label}`,
      platform.position.x - 135, platform.position.y + 30);
  }
}

/** Draw a dark bar on each platform that has a train standing at it now. */
function drawTrains(
  context: CanvasRenderingContext2D,
  platforms: readonly Platform[],
  trains: readonly TrainAtPlatform[],
) {
  for (const train of trains) {
    const platform = platforms.find((item) => item.platform_id === train.platform_id);
    if (!platform) continue;
    context.fillStyle = "#16191d";
    context.fillRect(platform.position.x - 100, platform.position.y - 8, 200, 16);
  }
}

/**
 * The true count is always labeled, even when the drawn markers are a sample.
 * Drawn in screen space, after the fit transform is dropped: the label is
 * chrome, so it must not scale or drift with the map.
 */
function drawPassengerCount(
  context: CanvasRenderingContext2D,
  dpr: number,
  shown: number,
  trueCount: number,
) {
  context.setTransform(1, 0, 0, 1, 0, 0);
  context.scale(dpr, dpr);
  context.fillStyle = "#16191d";
  context.font = "12px Arial";
  const label = shown < trueCount
    ? `Passengers: ${trueCount} (showing ${shown})`
    : `Passengers: ${trueCount}`;
  context.fillText(label, 12, 20);
}

/** Draw recorded map coordinates; seeking rebuilds rather than mutating sprites. */
export function StationCanvas() {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const data = usePlaybackStore((state) => state.data);
  const time = usePlaybackStore((state) => state.currentTime_s);
  const selected = usePlaybackStore((state) => state.selectedConnectionId);
  const followed = usePlaybackStore((state) => state.selectedPassengerId);
  const selectPassenger = usePlaybackStore((state) => state.selectPassenger);

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

  // Redraw the whole frame from the recorded snapshot whenever the data, time,
  // selection or view size changes. Each drawing step is its own function below.
  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!context || !canvas || !data) return;

    const view = chooseView(viewSize, data.map);
    const { scale, offsetX, offsetY } = fitLayout(data.map, view);
    const dpr = window.devicePixelRatio || 1;
    sizeCanvas(canvas, view, dpr);

    // Map space: device pixels, then the fit offset and scale.
    context.setTransform(1, 0, 0, 1, 0, 0);
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.scale(dpr, dpr);
    context.translate(offsetX, offsetY);
    context.scale(scale, scale);

    const snapshot = getNetworkSnapshot(data, time);
    // The selected corridor is derived from the same shared selection as the UI.
    const connection = data.connections.find((item) => item.id === selected);
    drawCorridors(context, data.corridors, connection?.corridor_id);
    drawPlatforms(context, data.platforms);
    drawTrains(context, data.platforms, snapshot.trains_at_platforms);

    // No incremental passenger state: pause and backward seeking stay exact.
    const { sampled, trueCount } = connectionSample(snapshot.passengers, selected, followed);
    for (const passenger of sampled) {
      drawPassengerMarker(context, passenger.position, passenger.phase);
    }
    const followedMarker = sampled.find((passenger) => passenger.passenger_id === followed);
    if (followedMarker) drawSelectionRing(context, followedMarker.position);
    if (selected) drawPassengerCount(context, dpr, sampled.length, trueCount);
  }, [data, time, selected, followed, viewSize]);

  if (!data) return <p className="station-message">Choose a connection to load a mock run.</p>;

  // A click follows the nearest drawn passenger, or clears the pick on empty space.
  const handleClick = (event: MouseEvent<HTMLCanvasElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const fit = fitLayout(data.map, chooseView(viewSize, data.map));
    const { sampled } = connectionSample(getNetworkSnapshot(data, time).passengers, selected, followed);
    selectPassenger(pickPassenger(sampled, { x: event.clientX - rect.left, y: event.clientY - rect.top }, fit));
  };
  const followingLabel = followed ? `, following passenger ${followed}` : "";
  return (
    <div ref={containerRef} className="station-canvas-wrap">
      <canvas ref={canvasRef} className="station-canvas" onClick={handleClick}
        width={data.map.width} height={data.map.height} role="img"
        aria-label={`${data.interchange.name} at ${time.toFixed(1)} simulation seconds${followingLabel}`}>
        Station schematic with platforms, transfer corridor, trains and passengers.
      </canvas>
    </div>
  );
}
