// AI contribution: 50% or more AI-generated
/**
 * Badge showing a parameter's confidence classification, its source name and,
 * when one is safe to open, a link to the source (US-7.1, Task 7.1.1).
 * Missing or invalid data reads "Unspecified" / "Source not specified".
 */
import {
  CLASSIFICATION_LABELS,
  getSafeSourceLink,
  normalizeClassification,
  type ParameterProvenance,
} from "../types/provenance";
import "./provenance-badge.css";

interface ProvenanceBadgeProps {
  parameterKey?: string;
  provenance?: ParameterProvenance | null;
}

export function ProvenanceBadge({
  parameterKey,
  provenance,
}: Readonly<ProvenanceBadgeProps>) {
  const classification = normalizeClassification(provenance?.classification);
  const badgeLabel = classification
    ? CLASSIFICATION_LABELS[classification]
    : "Unspecified";
  const badgeClass = classification
    ? `provenance-badge provenance-badge--${classification}`
    : "provenance-badge provenance-badge--unknown";

  const sourceName = provenance?.source_name?.trim() || "Source not specified";
  const safeLink = getSafeSourceLink(provenance?.source_link);

  return (
    <span
      className="provenance-meta"
      data-testid={parameterKey ? `provenance-${parameterKey}` : "provenance-meta"}
    >
      <span className={badgeClass}>{badgeLabel}</span>
      <span className="provenance-source">{sourceName}</span>
      {safeLink && (
        <a
          className="provenance-link"
          href={safeLink}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={
            parameterKey
              ? `Source link for ${parameterKey}: ${sourceName}`
              : `Source link: ${sourceName}`
          }
        >
          Source
        </a>
      )}
    </span>
  );
}