// AI contribution: 50% or more AI-generated
/**
 * Lists recorded hold decisions, marking refused and clamped decisions
 * distinctly from fully-applied ones, and showing the requested duration
 * alongside the applied one whenever a rule changed it (US-2.5,
 * Task 2.5.2, #57). Each decision also shows what the strategy saw next to
 * the true value, with the gap (US-2.1 demo steps 1 to 3, #39). Numbers are
 * rounded to whole seconds or passengers.
 *
 * Data is a fixture (web/src/data/decisions.ts) mirroring
 * simulator/control/decision.py HoldDecision and the Hold event, pending a
 * backend endpoint that serves recorded decisions for a run.
 */
import { decisionRecords, estimateRecords } from "../data/decisions";
import { decisionStatus, estimatesFor } from "../types/decision";
import type {
  EstimatesRecord,
  HoldDecisionRecord,
  SeenAndTrue,
} from "../types/decision";
import { usePlaybackStore } from "../store/usePlaybackStore";

/** Label shown for each outcome of the safety rules. */
const STATUS_LABEL: Record<string, string> = {
  applied: "Applied",
  clamped: "Clamped",
  refused: "Refused",
};

/** Row label, the seen and true pair, and the unit printed after each number. */
type Labelled = [label: string, value: SeenAndTrue, unit: string];

/** One row per estimated value, as plain numbers ready to print; a value with
 * nothing to predict is skipped. */
function estimateRows(record: EstimatesRecord) {
  // Train values first, then transfer groups, as in the backend record
  const values: Labelled[] = [
    ...record.trains.flatMap((train): Labelled[] => [
      [`${train.train_id} arrival`, train.predicted_arrival_s, " s"],
      [`${train.train_id} load`, train.onboard_load, ""],
    ]),
    ...record.transfers.flatMap((group): Labelled[] => [
      [`${group.group_id} still walking`, group.passenger_count, ""],
      [`${group.group_id} group size`, group.group_size, ""],
    ]),
  ];
  // A train with no next stop has no arrival, so there is no gap to show
  return values.flatMap(([label, value, unit]) =>
    value.seen === null || value.true === null
      ? []
      : [{ label, seen: value.seen, actual: value.true, unit }],
  );
}

/** Seen minus true, with a + sign so an estimate that is too late stands out. */
function signedGap(gap: number, unit: string) {
  const rounded = Math.round(gap);
  return `${rounded > 0 ? "+" : ""}${rounded}${unit}`;
}

/** Seen, true and gap for each value the strategy estimated at one decision. */
function EstimateTable({ record }: Readonly<{ record: EstimatesRecord }>) {
  return (
    // Named for screen readers, since the cells alone read as bare numbers
    <table className="decision-estimates" aria-label="Seen versus true">
      <thead>
        <tr>
          <th>Value</th>
          <th>Seen</th>
          <th>True</th>
          <th>Gap</th>
        </tr>
      </thead>
      <tbody>
        {estimateRows(record).map(({ label, seen, actual, unit }) => (
          // Labels are unique within one decision, so they work as React keys
          <tr key={label}>
            <td>{label}</td>
            <td>{`${Math.round(seen)}${unit}`}</td>
            <td>{`${Math.round(actual)}${unit}`}</td>
            <td>{signedGap(seen - actual, unit)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** One decision: outcome, hold length, reason, and what the strategy saw. */
function DecisionRow({
  decision,
  estimates,
}: Readonly<{
  decision: HoldDecisionRecord;
  estimates?: EstimatesRecord;
}>) {
  const status = decisionStatus(decision);
  // The requested length only matters when a rule shortened or refused it
  const wasChanged = status !== "applied";

  return (
    <li className={`decision-row decision-row--${status}`} data-status={status}>
      <span className="decision-train">{decision.train_id}</span>
      <span className="decision-status">{STATUS_LABEL[status]}</span>
      {/* Requested and applied when a rule changed the hold, else the length */}
      <span className="decision-duration">
        {wasChanged ? (
          <>
            <span className="decision-requested">
              requested {decision.requested_s}s
            </span>
            {" → "}
            <span className="decision-applied">
              applied {decision.applied_s}s
            </span>
          </>
        ) : (
          <span className="decision-applied">{decision.applied_s}s</span>
        )}
      </span>
      <small className="decision-reason">{decision.reason}</small>
      {/* Only runs with a prediction error model record estimates */}
      {estimates && <EstimateTable record={estimates} />}
    </li>
  );
}

/** Decisions reached so far at the selected connection's two platforms, each
 * with what the strategy saw when it decided. */
export function DecisionView() {
  const data = usePlaybackStore((state) => state.data);
  const time = usePlaybackStore((state) => state.currentTime_s);
  const selected = usePlaybackStore((state) => state.selectedConnectionId);
  const connection = data?.connections.find((item) => item.id === selected);
  // Reached by playback, inside the run, at either platform of the selected
  // connection, and at a platform that belongs to the station it names
  const visibleDecisions = decisionRecords.filter((decision) =>
    data && decision.time_s <= time && decision.time_s <= data.duration_s &&
    (decision.platform_id === connection?.from_platform_id ||
      decision.platform_id === connection?.to_platform_id) &&
    data.platforms.some((platform) => platform.platform_id === decision.platform_id &&
      platform.stop_id === decision.station_id),
  );
  // One row per visible decision, keyed by train and time, which never repeat
  return (
    <section className="panel decision-view" aria-label="Decisions">
      <span className="clock-heading">Decisions</span>
      <ul className="decision-list">
        {visibleDecisions.map((decision) => (
          <DecisionRow
            key={`${decision.train_id}-${decision.time_s}`}
            decision={decision}
            // The estimates taken at this same decision, if the run kept them
            estimates={estimatesFor(decision, estimateRecords)}
          />
        ))}
      </ul>
    </section>
  );
}
