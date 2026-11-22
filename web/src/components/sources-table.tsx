// AI contribution: 50% or more AI-generated
/**
 * Sources table (US-7.2, #319, #321): every simulation input with the value
 * used in this run, its label and its source, filtered by label. Each row
 * opens to show what the label means and a link to the source when there is
 * a safe one. An input with no recorded source says so instead of being blank.
 */
import { Fragment, useId, useState } from "react";
import { CLASSIFICATION_MEANINGS, type SourceRow } from "../lib/parameter-sources";
import {
  CLASSIFICATION_LABELS,
  getSafeSourceLink,
  type ConfidenceClassification,
} from "../types/provenance";
import "./sources.css";

type Filter = ConfidenceClassification | "all";

const FILTERS = Object.keys(CLASSIFICATION_LABELS) as ConfidenceClassification[];

/** The opened part of a row: label meaning, source and link, all in words. */
function SourceDetails({ row }: Readonly<{ row: SourceRow }>) {
  const link = getSafeSourceLink(row.sourceLink);
  return (
    <dl className="source-details">
      <dt>Label</dt>
      <dd>
        {row.classification
          ? `${CLASSIFICATION_LABELS[row.classification]}: ${CLASSIFICATION_MEANINGS[row.classification]}`
          : "No label recorded yet"}
      </dd>
      <dt>Source</dt>
      <dd>{row.sourceName ?? "No source recorded yet"}</dd>
      <dt>Link</dt>
      {/* noopener stops the source page reaching back into the app. */}
      <dd>{link ? <a href={link} target="_blank" rel="noopener noreferrer">{link}</a> : "None yet"}</dd>
    </dl>
  );
}

export function SourcesTable({ rows }: Readonly<{ rows: readonly SourceRow[] }>) {
  const filterLabel = useId();
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<string | null>(null);
  const count = (id: ConfidenceClassification) => rows.filter((row) => row.classification === id).length;
  // Inputs without a label only show under "All".
  const shown = filter === "all" ? rows : rows.filter((row) => row.classification === filter);

  return (
    <div className="sources-table">
      <fieldset className="segmented-control" aria-labelledby={filterLabel}>
        <span id={filterLabel} className="clock-heading">Filter by label</span>
        <button type="button" aria-pressed={filter === "all"} onClick={() => setFilter("all")}>All</button>
        {FILTERS.map((id) => (
          <button key={id} type="button" aria-pressed={filter === id}
            onClick={() => setFilter(id)}>{CLASSIFICATION_LABELS[id]} · {count(id)}</button>
        ))}
      </fieldset>

      <table>
        <thead>
          <tr><th>Value</th><th>Used in this run</th><th>Label</th><th>Source</th><th /></tr>
        </thead>
        <tbody>
          {shown.map((row) => {
            const isOpen = open === row.name;
            return (
              <Fragment key={row.name}>
                <tr>
                  <th scope="row">{row.label}</th>
                  <td>{row.value ?? "—"}</td>
                  <td>{row.classification ? CLASSIFICATION_LABELS[row.classification] : "—"}</td>
                  <td className={row.sourceName ? undefined : "source-missing"}>
                    {row.sourceName ?? "No source recorded yet"}
                  </td>
                  <td>
                    <button type="button" className="playback-button" aria-expanded={isOpen}
                      aria-label={`Details for ${row.label}`}
                      onClick={() => setOpen(isOpen ? null : row.name)}>{isOpen ? "Hide" : "Details"}</button>
                  </td>
                </tr>
                {isOpen && <tr><td colSpan={5}><SourceDetails row={row} /></td></tr>}
              </Fragment>
            );
          })}
        </tbody>
      </table>
      {shown.length === 0 && <p className="sources-empty">No inputs have this label.</p>}
    </div>
  );
}
