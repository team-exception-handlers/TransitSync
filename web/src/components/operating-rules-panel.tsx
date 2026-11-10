// AI contribution: 50% or more AI-generated
/**
 * Displays the active operating-rule set: the scenario's safety limits and
 * which rules clamp vs refuse a hold that violates them (US-2.5,
 * Task 2.5.1, #57).
 *
 * Data is a fixture (web/src/data/operating-rules.ts) mirroring
 * simulator/control/settings.py OperatingRulesConfig, pending a backend
 * endpoint that serves the active scenario's rules.
 */
import { operatingRules, operatingRulesConfig } from "../data/operating-rules";

export function OperatingRulesPanel() {
  return (
    <section className="panel operating-rules-panel" aria-label="Operating rules">
      <span className="clock-heading">Operating rules</span>

      <dl className="operating-rules-values">
        <div>
          <dt>Max hold time</dt>
          <dd>{operatingRulesConfig.max_hold_time}s</dd>
        </div>
        <div>
          <dt>Min safe gap</dt>
          <dd><span>{operatingRulesConfig.min_safe_gap}s</span> <small>Not enforced yet</small></dd>
        </div>
      </dl>

      <ul className="operating-rules-list">
        {operatingRules.map((rule) => (
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
