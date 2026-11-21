// AI contribution: 50% or more AI-generated
/**
 * Types, labels and validation helpers for parameter provenance (US-7.1):
 * the four confidence classifications and safe source links.
 */

/** The four confidence levels from US-7.1; mirrors VALID_CLASSIFICATIONS in the backend. */
export type ConfidenceClassification =
  | "measured"
  | "estimated"
  | "published"
  | "assumed";

/** One parameter's entry in GET /parameters, after parseParameterProvenance. */
export interface ParameterProvenance {
  // Already normalized by parseParameterProvenance; null means unknown or invalid.
  classification?: ConfidenceClassification | null;
  source_name?: string | null;
  source_link?: string | null;
}

/** Entries keyed by parameter name, such as "max_hold_time". */
export type ParameterProvenanceMap = Record<string, ParameterProvenance>;

/** The one place the display names live, so every badge uses the same words (#312). */
export const CLASSIFICATION_LABELS: Record<ConfidenceClassification, string> = {
  measured: "Measured",
  estimated: "Estimated",
  published: "Published",
  assumed: "Assumed",
};

/**
 * One of the four classifications, or null. The API can send any string, so
 * anything unknown reads "Unspecified" instead of inventing a level.
 */
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

/**
 * The link only if it is an absolute `http`/`https` URL. It goes straight into
 * an `href`, where a `javascript:` URL would run in the app when clicked.
 */
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
