"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { SeverityCounts } from "@/components/severity";
import { formatDateTime, shortSha } from "@/lib/format";
import type { ScorePoint } from "@/lib/score";

const HEIGHT = 220;
const PAD = { top: 16, right: 20, bottom: 28, left: 34 };
const TICKS = [0, 25, 50, 75, 100];

const shortDate = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "Europe/Paris" });

// One line, one hue: each point is one scanned commit, oldest on the left.
// Hollow points are incomplete scans (a scanner failed), so their score may be too kind.
export function ScoreTrend({ points }: { points: ScorePoint[] }) {
  const frame = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [active, setActive] = useState<number | null>(null);

  useEffect(() => {
    const node = frame.current;
    if (!node) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)));
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const plotW = Math.max(0, width - PAD.left - PAD.right);
  const plotH = HEIGHT - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (points.length === 1 ? plotW / 2 : (i / (points.length - 1)) * plotW);
  const y = (score: number) => PAD.top + (1 - score / 100) * plotH;
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.score).toFixed(1)}`).join(" ");
  const shown = active === null ? null : points[active];

  // The crosshair snaps to the nearest scan; the whole plot is the hit area, not the 8px dots.
  function onMove(event: React.PointerEvent<SVGRectElement>) {
    const left = event.currentTarget.getBoundingClientRect().left;
    const ratio = points.length === 1 ? 0 : (event.clientX - left) / plotW;
    setActive(Math.min(points.length - 1, Math.max(0, Math.round(ratio * (points.length - 1)))));
  }

  function onKey(event: React.KeyboardEvent<SVGSVGElement>) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const step = event.key === "ArrowLeft" ? -1 : 1;
    setActive((current) => Math.min(points.length - 1, Math.max(0, (current ?? points.length - 1) + step)));
  }

  return (
    <div>
      <div ref={frame} className="relative">
        {width > 0 && (
          <svg
            width={width}
            height={HEIGHT}
            role="img"
            aria-label={`Security score of the last ${points.length} completed scans, from ${points[0].score} to ${points[points.length - 1].score}. Use the arrow keys to read each scan.`}
            tabIndex={0}
            onKeyDown={onKey}
            onBlur={() => setActive(null)}
            className="block overflow-visible focus-visible:outline-offset-4"
          >
            {TICKS.map((tick) => (
              <g key={tick}>
                <line x1={PAD.left} x2={PAD.left + plotW} y1={y(tick)} y2={y(tick)} stroke="var(--rule)" strokeWidth={1} />
                <text x={PAD.left - 10} y={y(tick)} dy="0.32em" textAnchor="end" className="fill-muted font-mono text-[11px] tabular-nums">
                  {tick}
                </text>
              </g>
            ))}
            <text x={PAD.left} y={HEIGHT - 6} className="fill-muted font-mono text-[11px]">
              {shortDate.format(new Date(points[0].at))}
            </text>
            {points.length > 1 && (
              <text x={PAD.left + plotW} y={HEIGHT - 6} textAnchor="end" className="fill-muted font-mono text-[11px]">
                {shortDate.format(new Date(points[points.length - 1].at))}
              </text>
            )}

            <path d={path} fill="none" stroke="var(--signal)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />

            {shown && active !== null && (
              <line x1={x(active)} x2={x(active)} y1={PAD.top} y2={PAD.top + plotH} stroke="var(--ink)" strokeWidth={1} opacity={0.35} />
            )}

            {points.map((p, i) => (
              <circle
                key={p.scanId}
                cx={x(i)}
                cy={y(p.score)}
                r={active === i ? 5.5 : 4}
                fill={p.incomplete ? "var(--paper)" : "var(--signal)"}
                stroke={p.incomplete ? "var(--signal)" : "var(--paper)"}
                strokeWidth={2}
                paintOrder="stroke"
              />
            ))}

            <rect
              x={PAD.left}
              y={0}
              width={plotW}
              height={HEIGHT}
              fill="transparent"
              onPointerMove={onMove}
              onPointerLeave={() => setActive(null)}
            />
          </svg>
        )}

        {shown && active !== null && (
          <div
            className="pointer-events-none absolute top-0 z-10 w-56 border border-rule bg-surface px-3 py-2.5 text-[13px] shadow-[0_6px_20px_-12px_rgba(23,25,30,0.35)]"
            // Beside the crosshair, never on top of the point it describes.
            style={{ left: x(active) < width / 2 ? x(active) + 14 : Math.max(0, x(active) - 14 - 224) }}
            aria-hidden="true"
          >
            <p className="flex items-baseline justify-between gap-3">
              <span className="text-[20px] font-semibold">{shown.score}</span>
              <span className="text-muted">PR #{shown.pr} · <span className="font-mono">{shortSha(shown.sha)}</span></span>
            </p>
            <p className="mt-1 text-muted">{formatDateTime(shown.at)}</p>
            <div className="mt-2">
              <SeverityCounts severities={shown.severities} />
            </div>
            {shown.incomplete && <p className="mt-2 text-[12px] text-muted">Incomplete scan: a scanner failed.</p>}
          </div>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-[12px] text-muted">
        <span className="inline-flex items-center gap-2">
          <span className="size-2 rounded-full bg-signal" aria-hidden="true" />
          Complete scan
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="size-2 rounded-full border-2 border-signal" aria-hidden="true" />
          Incomplete scan
        </span>
      </div>

      <details className="mt-4 text-[13px]">
        <summary className="cursor-pointer text-muted hover:text-ink">Show as a table</summary>
        <table className="mt-3 w-full border-collapse text-left">
          <thead>
            <tr className="border-t border-ink font-mono text-[11px] tracking-[0.06em] text-muted uppercase">
              <th scope="col" className="py-2 pr-4 font-normal">Scan</th>
              <th scope="col" className="py-2 pr-4 font-normal">Date</th>
              <th scope="col" className="py-2 pr-4 font-normal">Issues</th>
              <th scope="col" className="py-2 text-right font-normal">Score</th>
            </tr>
          </thead>
          <tbody>
            {[...points].reverse().map((p) => (
              <tr key={p.scanId} className="border-t border-rule">
                <td className="py-2 pr-4">
                  <Link href={`/dashboard/scans/${p.scanId}`} className="underline-offset-4 hover:underline">
                    PR #{p.pr}
                  </Link>
                  <span className="ml-2 font-mono text-[12px] text-muted">{shortSha(p.sha)}</span>
                </td>
                <td className="py-2 pr-4 text-muted">{formatDateTime(p.at)}</td>
                <td className="py-2 pr-4">
                  <SeverityCounts severities={p.severities} />
                </td>
                <td className="py-2 text-right font-mono tabular-nums">
                  {p.score}
                  {p.incomplete && <span className="text-muted">*</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
