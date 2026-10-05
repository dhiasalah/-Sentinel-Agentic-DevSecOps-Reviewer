import argparse
import json
import logging
import sys
import traceback
from contextlib import nullcontext
from pathlib import Path
import getpass
import secrets
from langgraph.types import Command, StateSnapshot
from sentinel.approvals import fix_record
from sentinel.config import Settings
from sentinel.fix_graph import Decision, build_fix_graph, open_checkpoints
from sentinel.fixer import NotFixable, propose_fix
from sentinel.github.fix_pr import checkout_pr
from sentinel.graph import SCANNERS, build_graph
from sentinel.llm.router import build_router
from sentinel.models import Finding, TriagedIssue
from sentinel.policy import SEVERITY_ORDER, rank
from sentinel.sandbox import SandboxError, Verification, verify_fix
from sentinel.store import open_store

EXIT_OK, EXIT_ISSUES, EXIT_ERROR = 0, 1, 2
DEFAULT_DB = Path(".sentinel/approvals.sqlite")


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
    verify = commands.add_parser("verify", help="apply a patch to a copy of the repo in a sandbox, then re-scan it")
    verify.add_argument("path", type=Path, help="the folder that was scanned")
    verify.add_argument("--report", type=Path, required=True, help="JSON report written by `scan -o`")
    verify.add_argument("--issue", type=int, required=True, help="issue number in the report (1 = first)")
    verify.add_argument("--patch", type=Path, required=True, help="patch written by `fix -o`")
    verify.add_argument("-v", "--verbose", action="store_true", help="show detailed logs")
    propose = commands.add_parser("propose", help="fix one issue, verify it in the sandbox, then wait for a human")
    propose.add_argument("path", type=Path, nargs="?", help="the folder that was scanned (or use --pr)")
    propose.add_argument("--pr", help="owner/repo#12: fix the head of this GitHub PR instead of a local folder")
    propose.add_argument("--report", type=Path, required=True, help="JSON report written by `scan -o`")
    propose.add_argument("--issue", type=int, required=True, help="issue number in the report (1 = first)")
    propose.add_argument("--db", type=Path, default=DEFAULT_DB, help="where paused fixes are saved")
    propose.add_argument("-v", "--verbose", action="store_true", help="show detailed logs")
    review = commands.add_parser("review", help="show a paused fix, or approve / reject it")
    review.add_argument("id", help="the fix id printed by `propose`")
    decision = review.add_mutually_exclusive_group()
    decision.add_argument("--approve", metavar="PATCH_ID", help="approve this exact patch (its id is shown with the diff)")
    decision.add_argument("--reject", action="store_true", help="reject the patch")
    review.add_argument("--reason", default="", help="why you reject it")
    review.add_argument("--db", type=Path, default=DEFAULT_DB, help="where paused fixes are saved")
    review.add_argument("-v", "--verbose", action="store_true", help="show detailed logs")
    args = parser.parse_args(argv)
    if args.command == "propose" and (args.path is None) == (args.pr is None):
        parser.error("propose needs a folder or --pr (one of them, not both)")
    return args


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

def load_issue(report: Path, number: int) -> tuple[TriagedIssue, list[Finding]]:
    issues = [TriagedIssue.model_validate(item) for item in json.loads(report.read_text(encoding="utf-8"))]
    if not 1 <= number <= len(issues):
        raise ValueError(f"--issue must be between 1 and {len(issues)}")
    return issues[number - 1], [f for issue in issues for f in issue.findings]


def run_fix(args: argparse.Namespace) -> int:
    try:
        issue, all_findings = load_issue(args.report, args.issue)
        patch = propose_fix(issue, args.path, build_router(Settings()), all_findings)
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


def run_verify(args: argparse.Namespace) -> int:
    try:
        issue, all_findings = load_issue(args.report, args.issue)
        diff = args.patch.read_text(encoding="utf-8")
        result = verify_fix(args.path, diff, issue, all_findings, SCANNERS)
    except SandboxError as e:
        print(f"sentinel: patch rejected: {e}", file=sys.stderr)
        return EXIT_ISSUES
    except Exception as e:
        print(f"sentinel: verify failed: {type(e).__name__}: {e}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        return EXIT_ERROR
    show_verification(result)
    return EXIT_OK if result.verified else EXIT_ISSUES


def show_verification(result: Verification, file=None) -> None:
    print(f"sandbox: patch changes {', '.join(result.changed)}; re-scanned with {', '.join(result.scanners)}", file=file)
    for f in result.still_there:
        print(f"  still reported: {f.tool} {f.rule_id} at {f.file}:{f.line}", file=file)
    for f in result.new:
        print(f"  NEW: {f.tool} {f.rule_id} at {f.file}:{f.line}", file=file)
    for problem in result.problems:
        print(f"  problem: {problem}", file=file)
    print("verified: the issue is gone and nothing new appeared" if result.verified else "NOT verified", file=file)


def show_fix(fix_id: str, state: StateSnapshot) -> int:
    if state.interrupts:
        pending = state.interrupts[0].value
        print(pending["diff"], end="")
        print(f"sentinel: {pending['summary']} (by {pending['provider']}), "
              f"verified in the sandbox with {', '.join(pending['scanners'])}", file=sys.stderr)
        print(f"sentinel: fix {fix_id} is waiting for a human. Patch id: {pending['patch_id']}", file=sys.stderr)
        print(f"  approve: python -m sentinel review {fix_id} --approve {pending['patch_id']}", file=sys.stderr)
        print(f"  reject:  python -m sentinel review {fix_id} --reject --reason \"...\"", file=sys.stderr)
        return EXIT_OK
    values = state.values
    if not values:
        print(f"sentinel: no fix with id {fix_id}", file=sys.stderr)
        return EXIT_ERROR
    if "verification" in values and not values["verification"].verified:
        show_verification(values["verification"], file=sys.stderr)
    status = values.get("status", "unfinished (an error stopped it)")
    who = f" by {values['decided_by']} at {values['decided_at']}" if "decided_by" in values else ""
    why = f": {values['reason']}" if values.get("reason") else ""
    print(f"sentinel: fix {fix_id} {status}{who}{why}", file=sys.stderr)
    if values.get("pr_url"):
        print(f"sentinel: fix PR opened: {values['pr_url']}", file=sys.stderr)
    return EXIT_OK if status == "approved" else EXIT_ISSUES


def publish_fix(settings: Settings, fix_id: str, issue: TriagedIssue, target: dict | None, state: StateSnapshot) -> None:
    store = open_store(settings)
    if store is None or target is None or not state.interrupts:
        return
    try:
        repo_id = store.repo_id(target["repo"])
        if repo_id is None:
            return
        store.save_fix(fix_record(fix_id, repo_id, issue, target, state.interrupts[0].value))
        print(f"sentinel: fix {fix_id} is also waiting in the dashboard", file=sys.stderr)
    except Exception as e:
        print(f"sentinel: could not publish the fix to the dashboard ({type(e).__name__}): {e}", file=sys.stderr)


def sync_fix(settings: Settings, fix_id: str, state: StateSnapshot) -> None:
    store = open_store(settings)
    status = state.values.get("status")
    if store is None or not state.values.get("target") or status not in ("approved", "rejected", "outdated"):
        return
    try:
        store.update_fix(fix_id, {"status": status, "pr_url": state.values.get("pr_url")})
    except Exception as e:
        print(f"sentinel: could not update the dashboard ({type(e).__name__}): {e}", file=sys.stderr)


def run_propose(args: argparse.Namespace) -> int:
    fix_id = f"fix-{secrets.token_hex(4)}"
    config = {"configurable": {"thread_id": fix_id}}
    try:
        issue, all_findings = load_issue(args.report, args.issue)
        settings = Settings()
        where = checkout_pr(args.pr, settings) if args.pr else nullcontext((args.path, None))
        with open_checkpoints(args.db) as saver, where as (path, target):
            graph = build_fix_graph(build_router(settings), saver, settings)
            target = target and {**target, "fix_id": fix_id}
            graph.invoke({"path": str(path), "issue": issue, "all_findings": all_findings, "target": target}, config)
            state = graph.get_state(config)
            publish_fix(settings, fix_id, issue, target, state)
            return show_fix(fix_id, state)
    except Exception as e:
        print(f"sentinel: propose failed: {type(e).__name__}: {e}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        return EXIT_ERROR


def run_review(args: argparse.Namespace) -> int:
    config = {"configurable": {"thread_id": args.id}}
    try:
        settings = Settings()
        with open_checkpoints(args.db) as saver:
            graph = build_fix_graph(build_router(settings), saver, settings)
            state = graph.get_state(config)
            if (args.approve or args.reject) and not state.interrupts:
                print(f"sentinel: fix {args.id} is not waiting for a decision", file=sys.stderr)
            elif args.approve or args.reject:
                decision = Decision(decision="approve" if args.approve else "reject",
                                    patch_id=args.approve or state.interrupts[0].value["patch_id"],
                                    by=getpass.getuser(), reason=args.reason)
                graph.invoke(Command(resume=decision.model_dump()), config)
                state = graph.get_state(config)
                sync_fix(settings, args.id, state)
            return show_fix(args.id, state)
    except Exception as e:
        print(f"sentinel: review failed: {type(e).__name__}: {e}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        return EXIT_ERROR


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    sys.stdout.reconfigure(encoding="utf-8")
    if args.command == "fix":
        return run_fix(args)
    if args.command == "verify":
        return run_verify(args)
    if args.command == "propose":
        return run_propose(args)
    if args.command == "review":
        return run_review(args)


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
