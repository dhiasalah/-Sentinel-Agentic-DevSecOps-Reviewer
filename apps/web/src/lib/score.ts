import type { Scan, Severity } from "@/lib/types";

// Points lost per issue. Simple on purpose, so anyone can recompute a score by hand.
// Issues the AI calls false positives still count: the model can explain, it cannot make the score better.
export const PENALTY: Record<Severity, number> = { critical: 25, high: 10, medium: 4, low: 1, info: 0 };

export function securityScore(severities: Severity[]): number {
  return Math.max(0, 100 - severities.reduce((sum, s) => sum + PENALTY[s], 0));
}

export type ScorePoint = {
  scanId: number;
  pr: number;
  sha: string;
  at: string;
  score: number;
  incomplete: boolean;
  severities: Severity[];
};

// Oldest first. Failed or running scans have no score: they did not look at everything.
export function scoreHistory(scans: Scan[], limit = 30): ScorePoint[] {
  return scans
    .filter((s) => s.status === "done")
    .slice(0, limit)
    .reverse()
    .map((s) => ({
      scanId: s.id,
      pr: s.pr,
      sha: s.head_sha,
      at: s.started_at,
      score: securityScore(s.severities),
      incomplete: s.failed_scanners.length > 0,
      severities: s.severities,
    }));
}
