export function BrandMark({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" aria-hidden="true">
      <rect x="1" y="1" width="38" height="38" rx="13" fill="currentColor" />
      <path
        d="M12 27V13h6.5c4 0 6.5 2 6.5 5s-2.5 5-6.5 5H17v4"
        stroke="var(--surface,#fff)"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      <path
        d="m25 11 4 4-4 4"
        stroke="var(--surface,#fff)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
