"""Grade several benchmark reports together: the AI can answer differently each run."""
import argparse
from pathlib import Path

from score import DEFAULT_KEY, grade, load_json


def caught(vuln: dict) -> bool:
    return vuln["found"] and not vuln["dismissed"]


def summarize(results: list[dict]) -> dict:
    hits = {vuln["id"]: 0 for vuln in results[0]["vulns"]}
    for result in results:
        for vuln in result["vulns"]:
            hits[vuln["id"]] += caught(vuln)
    return {
        "runs": len(results),
        "vulns": len(hits),
        "decoys": len(results[0]["decoys"]),
        "caught": [sum(caught(vuln) for vuln in result["vulns"]) for result in results],
        "flagged": [sum(result["decoys"].values()) for result in results],
        "unplanned": [result["unplanned"] for result in results],
        "hits": hits,
    }


def render(summary: dict) -> str:
    runs, vulns, decoys = summary["runs"], summary["vulns"], summary["decoys"]
    worst = min(summary["caught"])
    per_run = lambda values: " / ".join(map(str, values))
    by_hits = lambda test: " ".join(vid for vid, n in summary["hits"].items() if test(n)) or "-"
    return "\n".join([
        f"runs            {runs}",
        f"caught          {per_run(summary['caught'])}  of {vulns}  -> worst run {worst}/{vulns} ({worst / vulns:.0%})",
        f"decoys flagged  {per_run(summary['flagged'])}  of {decoys}  -> worst run {max(summary['flagged'])}/{decoys}",
        f"unplanned       {per_run(summary['unplanned'])}  (issues matching no vuln and no decoy)",
        f"always caught   {by_hits(lambda n: n == runs)}",
        f"flaky           {by_hits(lambda n: 0 < n < runs)}",
        f"never caught    {by_hits(lambda n: n == 0)}",
    ])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Grade several benchmark reports and show what changes between runs.")
    parser.add_argument("reports", type=Path, nargs="+", help="JSON reports of the same benchmark target")
    parser.add_argument("--key", type=Path, default=DEFAULT_KEY, help="answer key (default: benchmark/expected.json)")
    args = parser.parse_args(argv)
    key = load_json(args.key)
    print(render(summarize([grade(key, load_json(report)) for report in args.reports])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
