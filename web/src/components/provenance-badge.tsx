// AI contribution: 50% or more AI-generated
/**
 * Badge showing a parameter's confidence classification, its source name and,
 * when one is safe to open, a link to the source (US-7.1, Task 7.1.1).
 * Missing or invalid data reads "Unspecified" / "Source not specified", so a
 * parameter without provenance is visibly unsourced rather than silently blank.
 */
import {
  CLASSIFICATION_LABELS,
  getSafeSourceLink,
  normalizeClassification,
  type ParameterProvenance,
} from "../types/provenance";
import "./provenance-badge.css";

interface ProvenanceBadgeProps {
  /** Key in GET /parameters, such as "max_hold_time"; used for the test ID. */
  parameterKey?: string;
  /** Readable name for screen readers, such as "Maximum hold"; the raw key would be read aloud. */
  label?: string;
  /** This parameter's entry; null or undefined renders the "unspecified" badge. */
  provenance?: ParameterProvenance | null;
}

export function ProvenanceBadge({
  parameterKey,
  label,
  provenance,
}: Readonly<ProvenanceBadgeProps>) {
  const classification = normalizeClassification(provenance?.classification);
  const badgeLabel = classification
    ? CLASSIFICATION_LABELS[classification]
    : "Unspecified";
  // The class picks the colour per classification; the label text carries the
  // meaning too, so the badge does not rely on colour alone.
  const badgeClass = classification
    ? `provenance-badge provenance-badge--${classification}`
    : "provenance-badge provenance-badge--unknown";

  const sourceName = provenance?.source_name?.trim() || "Source not specified";
  const safeLink = getSafeSourceLink(provenance?.source_link);
  const linkName = label ? `Source link for ${label}: ${sourceName}` : `Source link: ${sourceName}`;

  return (
    <span
      className="provenance-meta"
      data-testid={parameterKey ? `provenance-${parameterKey}` : "provenance-meta"}
    >
      <span className={badgeClass}>{badgeLabel}</span>
      <span className="provenance-source">{sourceName}</span>
      {safeLink && (
        // A new tab keeps the run on screen; noopener stops the source page
        // from reaching back into the app through window.opener.
        <a
          className="provenance-link"
          href={safeLink}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={linkName}
        >
          Source
        </a>
      )}
    </span>
  );
}
