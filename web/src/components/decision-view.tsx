// AI contribution: 50% or more AI-generated
/**
 * Lists recorded hold decisions, marking refused and clamped decisions
 * distinctly from fully-applied ones, and showing the requested duration
 * alongside the applied one whenever a rule changed it (US-2.5,
 * Task 2.5.2, #57).
 *
 * Data is a fixture (web/src/data/decisions.ts) mirroring
 * simulator/control/decision.py HoldDecision and the Hold event, pending a
 * backend endpoint that serves recorded decisions for a run.
 */
import { decisionRecords } from "../data/decisions";
import { decisionStatus } from "../types/decision";
import type { HoldDecisionRecord } from "../types/decision";
import { usePlaybackStore } from "../store/usePlaybackStore";

const STATUS_LABEL: Record<string, string> = {
  applied: "Applied",
  clamped: "Clamped",
  refused: "Refused",
};

function DecisionRow({ decision }: { decision: HoldDecisionRecord }) {
  const status = decisionStatus(decision);
  const wasChanged = status !== "applied";

  return (
    <li className={`decision-row decision-row--${status}`} data-status={status}>
      <span className="decision-train">{decision.train_id}</span>
      <span className="decision-status">{STATUS_LABEL[status]}</span>
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
    </li>
  );
}

export function DecisionView() {
  const data = usePlaybackStore((state) => state.data);
  const time = usePlaybackStore((state) => state.currentTime_s);
  const selected = usePlaybackStore((state) => state.selectedConnectionId);
  const connection = data?.connections.find((item) => item.id === selected);
  const visibleDecisions = decisionRecords.filter((decision) =>
    data && decision.time_s <= time && decision.time_s <= data.duration_s &&
    (decision.platform_id === connection?.from_platform_id ||
      decision.platform_id === connection?.to_platform_id) &&
    data.platforms.some((platform) => platform.platform_id === decision.platform_id &&
      platform.stop_id === decision.station_id),
  );
  return (
    <section className="panel decision-view" aria-label="Decisions">
      <span className="clock-heading">Decisions</span>
      <ul className="decision-list">
        {visibleDecisions.map((decision) => (
          <DecisionRow
            key={`${decision.train_id}-${decision.time_s}`}
            decision={decision}
          />
        ))}
      </ul>
    </section>
  );
}
