export function Wordmark() {
  return (
    <span className="inline-flex items-center gap-2.5">
      <svg viewBox="0 0 16 16" aria-hidden="true" className="size-4">
        <rect x="1" y="1" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" />
        <rect x="6" y="6" width="4" height="4" className="fill-signal" />
      </svg>
      <span className="font-mono text-[13px] font-medium tracking-[0.08em] uppercase">Sentinel</span>
    </span>
  );
}
