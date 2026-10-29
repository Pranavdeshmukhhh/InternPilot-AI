export function Skeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="skeleton-content" role="status" aria-label="Loading workspace">
      <span className="sr-only">Loading…</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton-row" aria-hidden="true">
          <span className="skeleton-mark" />
          <div className="skeleton-lines">
            <span />
            <span />
            <span />
          </div>
        </div>
      ))}
    </div>
  );
}
