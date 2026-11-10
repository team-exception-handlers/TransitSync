// AI contribution: 50% or more AI-generated
/**
 * Pure fit/scale math for the station canvas. Maps the fixture's fixed-size
 * map box into an arbitrary view box, preserving aspect ratio and centring
 * the result (letterbox) rather than stretching or clipping it.
 */

export interface Box {
  width: number;
  height: number;
}

export interface FitResult {
  /** Uniform scale factor applied to map-space coordinates. */
  scale: number;
  /** Letterbox offset (in view-space px) to add after scaling, to centre the map. */
  offsetX: number;
  offsetY: number;
  /** Rendered size of the scaled map, in view-space px. */
  renderWidth: number;
  renderHeight: number;
}

/**
 * Compute the uniform scale and centring offset that fits `map` inside
 * `view` without distorting its aspect ratio ("contain" fit, letterboxed).
 * Degenerate boxes (zero/negative/non-finite dimensions) fall back to an
 * identity, untranslated fit so callers never divide by zero or draw NaNs.
 */
export function fitLayout(map: Box, view: Box): FitResult {
  const mapValid =
    Number.isFinite(map.width) &&
    Number.isFinite(map.height) &&
    map.width > 0 &&
    map.height > 0;

  const viewValid =
    Number.isFinite(view.width) &&
    Number.isFinite(view.height) &&
    view.width > 0 &&
    view.height > 0;

  if (!mapValid || !viewValid) {
    return {
      scale: 1,
      offsetX: 0,
      offsetY: 0,
      renderWidth: mapValid ? map.width : 0,
      renderHeight: mapValid ? map.height : 0,
    };
  }

  const scale = Math.min(view.width / map.width, view.height / map.height);

  const renderWidth = map.width * scale;
  const renderHeight = map.height * scale;

  return {
    scale,
    offsetX: (view.width - renderWidth) / 2,
    offsetY: (view.height - renderHeight) / 2,
    renderWidth,
    renderHeight,
  };
}
