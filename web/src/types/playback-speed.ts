// AI contribution: 50% or more AI-generated
/** The four supported factors from US-3.4 (#68) and the Figma speed component. */
export const PLAYBACK_SPEEDS = [0.5, 1, 2, 10] as const;
export type PlaybackSpeed = typeof PLAYBACK_SPEEDS[number];
