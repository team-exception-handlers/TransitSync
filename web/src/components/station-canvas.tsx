// AI contribution: 50% or more AI-generated
/**
 * Station-view Canvas consumer of Person 9's deterministic playback snapshots.
 * It uses fixture coordinates directly; it does not introduce a second mutable
 * simulation model, passenger positions or playback timer.
 */
import { useEffect, useRef } from "react";
import { getNetworkSnapshot } from "../lib/getNetworkSnapshot";
import { usePlaybackStore } from "../store/usePlaybackStore";

/** Draw recorded map coordinates; seeking rebuilds rather than mutating sprites. */
export function StationCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const data = usePlaybackStore((state) => state.data);
  const time = usePlaybackStore((state) => state.currentTime_s);
  const selected = usePlaybackStore((state) => state.selectedConnectionId);

  useEffect(() => {
    const context = canvasRef.current?.getContext("2d");
    if (!context || !data) return;
    const snapshot = getNetworkSnapshot(data, time);
    context.clearRect(0, 0, data.map.width, data.map.height);

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
    for (const passenger of snapshot.passengers) {
      if (passenger.connection_id !== selected) continue;
      context.beginPath();
      context.arc(passenger.position.x, passenger.position.y, 4, 0, 2 * Math.PI);
      context.fillStyle = passenger.phase === "boarding" ? "#007b78" : "#16191d";
      context.fill();
    }
  }, [data, time, selected]);

  if (!data) return <p className="station-message">Choose a connection to load a mock run.</p>;
  return (
    <canvas ref={canvasRef} className="station-canvas"
      width={data.map.width} height={data.map.height}
      role="img" aria-label={`${data.interchange.name} at ${time.toFixed(1)} simulation seconds`}>
      Station schematic with platforms, transfer corridor, trains and passengers.
    </canvas>
  );
}
