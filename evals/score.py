"""Grade a Sentinel JSON report against the benchmark answer key."""
import argparse
import json
import re
from pathlib import Path

SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]
CWE_ID = re.compile(r"CWE-\d+")
DEFAULT_KEY = Path(__file__).parent / "benchmark" / "expected.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def hits(issues: list[dict], item: dict) -> list[tuple[dict, dict]]:
    first, last = item["lines"]
    return [
        (issue, finding)
        for issue in issues
        for finding in issue["findings"]
        if finding["file"].replace("\\", "/") == item["file"] and first <= finding["line"] <= last
    ]


def grade_vuln(vuln: dict, issues: list[dict]) -> dict:
    matched = hits(issues, vuln)
    got_cwes = {cwe for _, finding in matched for text in finding["cwe"] for cwe in CWE_ID.findall(text)}
    top = min((issue["severity"] for issue, _ in matched), key=SEVERITY_ORDER.index, default=None)
    return {
        **vuln,
        "found": bool(matched),
        "dismissed": bool(matched) and all(issue["false_positive"] for issue, _ in matched),
        "cwe_ok": bool(got_cwes & set(vuln["cwes"])),
        "severity_ok": top is not None and SEVERITY_ORDER.index(top) <= SEVERITY_ORDER.index(vuln["severity"]),
        "got_cwes": sorted(got_cwes),
        "got_severity": top,
    }


def decoy_flagged(decoy: dict, issues: list[dict]) -> bool:
    return any(not issue["false_positive"] for issue, _ in hits(issues, decoy))


def unplanned(issues: list[dict], key: dict) -> int:
    items = key["vulns"] + key["decoys"]
    return sum(1 for issue in issues if not any(hits([issue], item) for item in items))


def grade(key: dict, issues: list[dict]) -> dict:
    return {
        "vulns": [grade_vuln(vuln, issues) for vuln in key["vulns"]],
        "decoys": {decoy["id"]: decoy_flagged(decoy, issues) for decoy in key["decoys"]},
        "unplanned": unplanned(issues, key),
    }


def render(result: dict) -> str:
    vulns, decoys = result["vulns"], result["decoys"]
    found = [r for r in vulns if r["found"]]
    lines = [
        f"detection       {len(found)}/{len(vulns)} ({len(found) / len(vulns):.0%})",
        f"right CWE       {sum(r['cwe_ok'] for r in found)}/{len(found)}",
        f"severity ok     {sum(r['severity_ok'] for r in found)}/{len(found)}",
        f"dismissed       {sum(r['dismissed'] for r in found)}  (real vulns the AI called false positive)",
        f"decoys flagged  {sum(decoys.values())}/{len(decoys)}  {' '.join(k for k, v in decoys.items() if v)}",
        f"unplanned       {result['unplanned']}  (issues that match no vuln and no decoy)",
        "",
        "found:",
    ]
    for r in found:
        problems = []
        if not r["cwe_ok"]:
            problems.append(f"got {'/'.join(r['got_cwes']) or 'none'} (want {'/'.join(r['cwes'])})")
        if not r["severity_ok"]:
            problems.append(f"severity {r['got_severity']} (want {r['severity']}+)")
        if r["dismissed"]:
            problems.append("AI called it a false positive")
        lines.append(f"  {r['id']} {r['title']:32} {'; '.join(problems) or 'ok'}")
    missed: dict[str, list[str]] = {}
    for r in vulns:
        if not r["found"]:
            missed.setdefault(r["scanner"], []).append(r["id"])
    lines.append("missed, by the scanner that should catch it:")
    for scanner, ids in sorted(missed.items()):
        lines.append(f"  {scanner:9} {len(ids)}: {' '.join(ids)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Grade a Sentinel JSON report against the benchmark answer key.")
    parser.add_argument("report", type=Path, help="output of: python -m sentinel scan <target> -o <report>")
    parser.add_argument("--key", type=Path, default=DEFAULT_KEY, help="answer key (default: benchmark/expected.json)")
    args = parser.parse_args(argv)
    print(render(grade(load_json(args.key), load_json(args.report))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
