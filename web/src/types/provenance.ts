// AI contribution: 50% or more AI-generated
/**
 * Shared types, classification labels, and validation helpers for parameter
 * provenance metadata (US-7.1).
 *
 * Normalizes confidence classifications (`measured`, `estimated`, `published`,
 * `assumed`) and sanitizes external `http`/`https` source links before UI
 * rendering.
 */
export type ConfidenceClassification =
  | "measured"
  | "estimated"
  | "published"
  | "assumed";

export interface ParameterProvenance {
  // Already normalized by parseParameterProvenance; null means unknown or invalid.
  classification?: ConfidenceClassification | null;
  source_name?: string | null;
  source_link?: string | null;
}

export type ParameterProvenanceMap = Record<string, ParameterProvenance>;

export const CLASSIFICATION_LABELS: Record<ConfidenceClassification, string> = {
  measured: "Measured",
  estimated: "Estimated",
  published: "Published",
  assumed: "Assumed",
};

export function normalizeClassification(
  value?: string | null,
): ConfidenceClassification | null {
  if (!value) return null;
  const normalized = value.trim().toLowerCase();
  if (
    normalized === "measured" ||
    normalized === "estimated" ||
    normalized === "published" ||
    normalized === "assumed"
  ) {
    return normalized;
  }
  return null;
}

export function getSafeSourceLink(link?: string | null): string | null {
  if (!link) return null;
  const trimmed = link.trim();
  if (!trimmed) return null;
  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol === "https:" || parsed.protocol === "http:") {
      return parsed.toString();
    }
    return null;
  } catch {
    return null;
  }
}