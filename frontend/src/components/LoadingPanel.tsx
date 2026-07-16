interface LoadingPanelProps {
  label: string;
}

export function LoadingPanel({ label }: LoadingPanelProps) {
  return (
    <div className="panel loading-panel" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}
