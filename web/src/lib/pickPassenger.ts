// AI contribution: 50% or more AI-generated
/**
 * Click hit-testing for the station canvas (#237): turns a click in screen
 * pixels back into map coordinates and finds the nearest drawn marker.
 */
import type { FitResult } from "./fitLayout";
import type { PassengerPosition, Point } from "../types/stationView";

/** Distance from a marker's centre that still picks it, in screen px (markers are 4 to 5 px). */
export const PICK_RADIUS_PX = 8;

type Fit = Pick<FitResult, "scale" | "offsetX" | "offsetY">;

/**
 * ID of the drawn passenger nearest a click (CSS px inside the canvas), or
 * null on empty space. Ties go to the lower ID, never to array order.
 */
export function pickPassenger(
  markers: readonly PassengerPosition[],
  screen: Point,
  fit: Fit,
): string | null {
  const x = (screen.x - fit.offsetX) / fit.scale;
  const y = (screen.y - fit.offsetY) / fit.scale;
  // The radius is fixed on screen, so it grows in map space as the map shrinks.
  const radius = PICK_RADIUS_PX / fit.scale;

  let bestId: string | null = null;
  let bestDistance = Infinity;
  for (const marker of markers) {
    const distance = Math.hypot(marker.position.x - x, marker.position.y - y);
    const closer = distance < bestDistance
      || (distance === bestDistance && bestId !== null && marker.passenger_id < bestId);
    if (distance <= radius && closer) {
      bestId = marker.passenger_id;
      bestDistance = distance;
    }
  }
  return bestId;
}
