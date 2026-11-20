// AI contribution: 50% or more AI-generated
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
}: ProvenanceBadgeProps) {
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