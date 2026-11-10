// AI contribution: 50% or more AI-generated
/**
 * One segmented-button row of the run settings panel, for a setting with a
 * few fixed values (passenger flow, disruption on/off). It reuses the
 * `.segmented-control` style of the speed and connection selectors, so a
 * pressed button means the same thing everywhere in the station view.
 */
import { useId } from "react";

interface SettingChoiceProps<Value extends string | boolean> {
  label: string;
  options: readonly Value[];
  value: Value;
  /** Button text for one option. */
  format: (option: Value) => string;
  onChange: (option: Value) => void;
  /** Optional sentence under the buttons saying what the setting does. */
  note?: string;
}

/** A labelled group of toggle buttons; `aria-pressed` marks the active one. */
export function SettingChoice<Value extends string | boolean>({
  label, options, value, format, onChange, note,
}: Readonly<SettingChoiceProps<Value>>) {
  const labelId = useId();
  return (
    <div className="setting">
      <div className="setting-top">
        <span className="setting-label" id={labelId}>{label}</span>
        <div className="segmented-control setting-choice" role="group" aria-labelledby={labelId}>
          {options.map((option) => (
            <button key={String(option)} type="button" aria-pressed={option === value}
              onClick={() => onChange(option)}>
              {format(option)}
            </button>
          ))}
        </div>
      </div>
      {note !== undefined && <p className="setting-note">{note}</p>}
    </div>
  );
}
