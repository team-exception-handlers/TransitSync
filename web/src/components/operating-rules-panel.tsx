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
import { runOperatingRules, runRuleCheck } from "../lib/runOperatingRules";
import { usePlaybackStore } from "../store/usePlaybackStore";
import type { RuleCheck } from "../types/operatingRules";

/**
 * The post-run check of the whole event log (#400): "Passed", or each
 * violation. Stated in words, not only color, so it reads without color vision.
 */
function RuleCheckResult({ check }: Readonly<{ check: RuleCheck }>) {
  if (check.passed) {
    return <p className="rule-check rule-check--passed">Rule check: passed, no rule broken in this run</p>;
  }
  const count = check.violations.length;
  return (
    <div className="rule-check rule-check--failed">
      <p>Rule check: failed, {count} {count === 1 ? "violation" : "violations"}</p>
      <ul>
        {check.violations.map((item) => (
          <li key={`${item.rule}-${item.subject_id}-${item.time_s}`}>{item.message}</li>
        ))}
      </ul>
    </div>
  );
}

export function OperatingRulesPanel() {
  const data = usePlaybackStore((state) => state.data);
  const fromRun = useMemo(() => runOperatingRules(data), [data]);
  // Mock playback and older cached runs have no check, so nothing is shown.
  const ruleCheck = useMemo(() => runRuleCheck(data), [data]);
  const config = fromRun?.config ?? operatingRulesConfig;
  const rules = fromRun?.rules ?? operatingRules;
  return (
    <section className="panel operating-rules-panel" aria-label="Operating rules">
      <span className="clock-heading">Operating rules</span>

      <dl className="operating-rules-values">
        <div>
          <dt>Max hold time</dt>
          <dd>{config.max_hold_time}s</dd>
        </div>
        <div>
          <dt>Min safe gap</dt>
          <dd><span>{config.min_safe_gap}s</span> <small>Not enforced yet</small></dd>
        </div>
      </dl>

      {ruleCheck && <RuleCheckResult check={ruleCheck} />}

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
