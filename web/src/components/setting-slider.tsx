// AI contribution: 50% or more AI-generated
/**
 * One labelled slider row of the run settings panel, following the Scenario
 * setup mockup: label on the left, the current value in monospace on the
 * right, the range input underneath, and an optional "?" help note.
 *
 * It is presentational: the value and the change handler come from the caller,
 * so the same row serves every numeric setting.
 */
import { useId, useState } from "react";
import type { SettingRange } from "../lib/run-settings";

interface SettingSliderProps {
  label: string;
  value: number;
  range: SettingRange;
  /** Text shown for a value, with its unit (for example "45 s"). */
  format: (value: number) => string;
  onChange: (value: number) => void;
  disabled?: boolean;
  /** Plain-language explanation opened by the "?" button, if any. */
  help?: string;
}

/** A range input whose label, value and help text are linked for assistive tech. */
export function SettingSlider({
  label, value, range, format, onChange, disabled = false, help,
}: Readonly<SettingSliderProps>) {
  const inputId = useId();
  const helpId = useId();
  const [helpOpen, setHelpOpen] = useState(false);
  const text = format(value);

  return (
    <div className="setting">
      <div className="setting-top">
        <label htmlFor={inputId}>{label}</label>
        {help !== undefined && (
          <button type="button" className="setting-help" aria-label={`What is ${label.toLowerCase()}?`}
            aria-expanded={helpOpen} aria-controls={helpId}
            onClick={() => setHelpOpen((open) => !open)}>
            <span aria-hidden="true">?</span>
          </button>
        )}
        {/* A span, not <output>: output has the "status" role, which the
            page reserves for its one run-status line. The slider itself
            announces this text through aria-valuetext. */}
        <span className="setting-value">{text}</span>
      </div>
      {/* Kept in the DOM while closed so aria-controls always has a target. */}
      {help !== undefined && (
        <p id={helpId} role="note" className="setting-help-text" hidden={!helpOpen}>{help}</p>
      )}
      <input id={inputId} type="range" min={range.min} max={range.max} step={range.step}
        value={value} disabled={disabled} aria-valuetext={text}
        onChange={(event) => onChange(Number(event.target.value))} />
    </div>
  );
}
