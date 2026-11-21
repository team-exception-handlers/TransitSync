// AI contribution: 50% or more AI-generated
/**
 * Displays the active operating-rule set: the scenario's safety limits and
 * which rules clamp vs refuse a hold that violates them (US-2.5,
 * Task 2.5.1, #57).
 *
 * A simulated run supplies the rules it used (lib/runOperatingRules.ts), so
 * the limits match the run settings, such as the chosen maximum hold. Mock
 * playback uses the fixture in web/src/data/operating-rules.ts.
 */
import { useMemo } from "react";
import { operatingRules, operatingRulesConfig } from "../data/operating-rules";
import { runOperatingRules } from "../lib/runOperatingRules";
import { usePlaybackStore } from "../store/usePlaybackStore";
import type { ParameterProvenanceMap } from "../types/provenance";
import { ProvenanceBadge } from "./provenance-badge";

interface OperatingRulesPanelProps {
  /** Parameter sources from GET /parameters, shown beside each limit. */
  provenance?: ParameterProvenanceMap;
}

export function OperatingRulesPanel({
  provenance,
}: Readonly<OperatingRulesPanelProps>) {
  const data = usePlaybackStore((state) => state.data);
  const fromRun = useMemo(() => runOperatingRules(data), [data]);
  const config = fromRun?.config ?? operatingRulesConfig;
  const rules = fromRun?.rules ?? operatingRules;
  return (
    <section className="panel operating-rules-panel" aria-label="Operating rules">
      <span className="clock-heading">Operating rules</span>

      <dl className="operating-rules-values">
        <div>
          <dt>Max hold time</dt>
          <dd><span>{config.max_hold_time}s</span>{" "}
            <ProvenanceBadge
              parameterKey="max_hold_time"
              label="Maximum hold"
              provenance={provenance?.max_hold_time}
            /></dd>
        </div>
        <div>
          <dt>Min safe gap</dt>
          <dd><span>{config.min_safe_gap}s</span> {" "}
            <ProvenanceBadge
              parameterKey="min_safe_gap"
              label="Minimum safe gap"
              provenance={provenance?.min_safe_gap}
            />{" "}<small>Not enforced yet</small></dd>
        </div>
      </dl>

      <ul className="operating-rules-list">
        {rules.map((rule) => (
          <li
            key={rule.name}
            className={`operating-rule operating-rule--${rule.action.toLowerCase()}`}
          >
            <span className="operating-rule-name">{rule.name}</span>
            <span
              className="operating-rule-action"
              data-action={rule.action}
            >
              {rule.action}
            </span>
            <small>{rule.description}</small>
            {rule.name === "headway_violation" && (
              <small>Configured action only; headway checking is not enforced yet.</small>
            )}
            {rule.name === "one_hop_violation" && (
              <small>Always refuses; the configured action is not used yet.</small>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
