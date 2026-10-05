import argparse
import json
import logging
import sys
import traceback
from pathlib import Path

from sentinel.config import Settings
from sentinel.fixer import NotFixable, propose_fix
from sentinel.graph import build_graph
from sentinel.llm.router import build_router
from sentinel.models import TriagedIssue
from sentinel.policy import SEVERITY_ORDER, rank


EXIT_OK, EXIT_ISSUES, EXIT_ERROR = 0, 1, 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="sentinel", description="Scan a folder and print a triaged security report.")
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan", help="scan a local folder")
    scan.add_argument("path", type=Path, help="folder to scan")
    scan.add_argument("--format", choices=["text", "json"], default="text", help="text for humans, json for robots")
    scan.add_argument("--fail-on", choices=SEVERITY_ORDER, default="high",
                      help="exit code 1 if an issue is at least this severe (default: high)")
    scan.add_argument("-o", "--output", type=Path, help="also write the JSON report to this file (UTF-8)")
    scan.add_argument("-v", "--verbose", action="store_true", help="show detailed logs")
    fix = commands.add_parser("fix", help="propose a patch for one issue of a JSON report (writes nothing)")
    fix.add_argument("path", type=Path, help="the folder that was scanned")
    fix.add_argument("--report", type=Path, required=True, help="JSON report written by `scan -o`")
    fix.add_argument("--issue", type=int, required=True, help="issue number in the report (1 = first)")
    fix.add_argument("-o", "--output", type=Path, help="also write the patch to this file (UTF-8, for git apply)")
    fix.add_argument("-v", "--verbose", action="store_true", help="show detailed logs")

    return parser.parse_args(argv)


def render_text(issues: list[TriagedIssue], finding_count: int) -> str:
    if not issues:
        return "No issues found."
    lines = []
    for issue in issues:
        flag = "  (AI thinks: false positive)" if issue.false_positive else ""
        where = ", ".join(dict.fromkeys(f"{f.file}:{f.line}" for f in issue.findings))
        lines.append(f"[{issue.severity.upper():8}] {issue.title}{flag}")
        lines.append(f"  at:  {where}")
        for reason in issue.review_reasons:
            lines.append(f"  ⚠ needs human review: {reason}")
        lines.append(f"  why: {issue.explanation}")
        lines.append(f"  fix: {issue.fix}")
        lines.append("")
    lines.append(f"{finding_count} scanner findings -> {len(issues)} issues")
    return "\n".join(lines)


def render_json(issues: list[TriagedIssue]) -> str:
    return json.dumps([issue.model_dump() for issue in issues], indent=2, ensure_ascii=False)


def exit_code(issues: list[TriagedIssue], fail_on: str) -> int:
    if any(rank(issue.severity) <= rank(fail_on) for issue in issues):
        return EXIT_ISSUES
    return EXIT_OK

def run_fix(args: argparse.Namespace) -> int:
    try:
        issues = [TriagedIssue.model_validate(item) for item in json.loads(args.report.read_text(encoding="utf-8"))]
        if not 1 <= args.issue <= len(issues):
            raise ValueError(f"--issue must be between 1 and {len(issues)}")
        patch = propose_fix(issues[args.issue - 1], args.path, build_router(Settings()),
                            [f for issue in issues for f in issue.findings])
    except NotFixable as e:
        print(f"sentinel: issue {args.issue} is not fixed automatically: {e}", file=sys.stderr)
        return EXIT_ISSUES
    except Exception as e:
        print(f"sentinel: fix failed: {type(e).__name__}: {e}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        return EXIT_ERROR
    print(f"sentinel: {patch.summary} (by {patch.provider})", file=sys.stderr)
    if not patch.diff:
        return EXIT_ISSUES
    if args.output:
        args.output.write_text(patch.diff, encoding="utf-8", newline="")
    print(patch.diff, end="")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    sys.stdout.reconfigure(encoding="utf-8")
    if args.command == "fix":
        return run_fix(args)

    try:
        result = build_graph(build_router(Settings())).invoke({"path": str(args.path)})
        findings, issues, failures = result["findings"], result["issues"], result["failures"]

    except Exception as e:
        print(f"sentinel: scan failed: {type(e).__name__}: {e}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        return EXIT_ERROR
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render_json(issues), encoding="utf-8")
    print(render_json(issues) if args.format == "json" else render_text(issues, len(findings)))
    for failure in failures:
        print(f"sentinel: scanner {failure.scanner} failed ({failure.error}), the report is incomplete", file=sys.stderr)
    return EXIT_ERROR if failures else exit_code(issues, args.fail_on)
