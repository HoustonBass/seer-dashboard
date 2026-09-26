// Hand-rolled switch (no external component library — this is a personal
// project, not on Home Depot's internal design system). Styled off the same
// tokens as everything else so it reads as part of the app, not a bolted-on
// widget.
export default function Toggle({ checked, onChange, disabled, title }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      title={title}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
        checked ? "bg-[var(--available)]" : "bg-[var(--rule-strong)]"
      }`}
    >
      <span
        className={`inline-block h-3.5 w-3.5 transform rounded-full bg-[var(--surface-raised)] transition-transform ${
          checked ? "translate-x-[18px]" : "translate-x-[3px]"
        }`}
      />
    </button>
  );
}
