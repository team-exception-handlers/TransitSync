// AI contribution: 50% or more AI-generated
/**
 * One labelled slider row of the run settings panel, following the Scenario
 * setup mockup: label on the left, the current value in monospace on the
 * right, the range input underneath, and an optional "?" help note.
 *
 * It is presentational: the value and the change handler come from the caller,
 * so the same row serves every numeric setting.
 *
 * With `onValidity`, the row also gets a number box for typing an exact value
 * (#256). A typed value is checked by `validateSetting` first: a valid one is
 * passed to `onChange`, an invalid one stays in the box with its error shown
 * underneath and reported through `onValidity`, and never reaches the store.
 */
import { useEffect, useId, useState } from "react";
import { validateSetting, type SettingRange } from "../lib/run-settings";

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
  /** Adds the number box; called with the entry's error, or null once it is valid. */
  onValidity?: (error: string | null) => void;
}

/** A range input whose label, value and help text are linked for assistive tech. */
export function SettingSlider({
  label, value, range, format, onChange, disabled = false, help, onValidity,
}: Readonly<SettingSliderProps>) {
  const inputId = useId();
  const helpId = useId();
  const errorId = useId();
  const [helpOpen, setHelpOpen] = useState(false);
  // Text typed in the number box; null shows the stored value instead.
  const [typed, setTyped] = useState<string | null>(null);
  // A new value from outside (the slider, a preset, Reset) replaces any
  // half-typed entry. Adjusting state while rendering is React's documented
  // way to reset state when a prop changes, without an extra render pass.
  const [shownValue, setShownValue] = useState(value);
  if (shownValue !== value) {
    setShownValue(value);
    setTyped(null);
  }
  const text = format(value);
  const error = typed === null ? null : validateSetting(label, Number(typed), range);
  // An empty box is Number("") === 0, so it is checked as text.
  const entryError = typed?.trim() === "" ? `${label}: enter a number` : error;

  // The parent collects every row's error to block "Run scenario".
  useEffect(() => onValidity?.(entryError), [entryError, onValidity]);

  /** Keep the typed text, and pass it on only once it is a valid value. */
  function onType(next: string) {
    setTyped(next);
    const number = Number(next);
    if (next.trim() !== "" && validateSetting(label, number, range) === null) onChange(number);
  }

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
        {onValidity !== undefined && (
          <input type="number" className="setting-entry" aria-label={`${label} value`}
            min={range.min} max={range.max} step={range.step} disabled={disabled}
            value={typed ?? String(value)} aria-invalid={entryError !== null}
            aria-describedby={entryError === null ? undefined : errorId}
            onChange={(event) => onType(event.target.value)} />
        )}
      </div>
      {entryError !== null && (
        <p id={errorId} className="setting-error">{entryError}</p>
      )}
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
