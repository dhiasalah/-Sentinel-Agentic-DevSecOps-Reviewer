import logging
import operator
from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from sentinel.llm.router import LLMRouter
from sentinel.mcp_scanners import call_scanner
from sentinel.models import Finding, ScanEvent, ScannerFailure, TriagedIssue
from sentinel.planner import choose_scanners, list_files
from sentinel.triage import triage

log = logging.getLogger(__name__)

Scanner = Callable[[Path], list[Finding]]


@dataclass(frozen=True)
class ScannerSpec:
    run: Scanner
    files: tuple[str, ...]


SCANNERS: dict[str, ScannerSpec] = {
    "gitleaks": ScannerSpec(
        run=lambda path: call_scanner("gitleaks", path),
        files=("*",),
    ),
    "semgrep": ScannerSpec(
        run=lambda path: call_scanner("semgrep", path),
        files=("*.py",),
    ),
    "trivy": ScannerSpec(
        run=lambda path: call_scanner("trivy", path),
        files=("requirements*.txt", "pipfile.lock", "poetry.lock", "uv.lock", "package-lock.json", "yarn.lock",
               "pnpm-lock.yaml", "go.mod", "cargo.lock", "gemfile.lock", "composer.lock", "pom.xml"),
    ),
    "checkov": ScannerSpec(
        run=lambda path: call_scanner("checkov", path),
        files=("dockerfile", "dockerfile.*", "*.dockerfile", "*.tf", "*.yaml", "*.yml"),
    ),


}


class ScanState(TypedDict):
    path: str
    scanners: list[str]
    findings: Annotated[list[Finding], operator.add]
    failures: Annotated[list[ScannerFailure], operator.add]
    issues: list[TriagedIssue]


class ScannerTask(TypedDict):
    path: str
    scanner: str

def emit(**event) -> None:
    """Report progress to whoever streams the graph (the worker). A no-op under plain invoke()."""
    get_stream_writer()(ScanEvent(**event))


def make_plan(enabled: Collection[str] | None):
    def plan(state: ScanState) -> dict:
        files = list_files(Path(state["path"]))
        relevant = choose_scanners({name: spec.files for name, spec in SCANNERS.items()}, files)
        if files is None:
            log.warning("plan: repo too big or unreadable, running every scanner")
        scanners = [name for name in relevant if enabled is None or name in enabled]
        for name in relevant:
            if name not in scanners:
                emit(stage="scanner", status="skipped", scanner=name)
        log.info("plan: %s (turned off in settings: %s)", scanners, sorted(set(relevant) - set(scanners)) or "none")
        emit(stage="plan", status="ok", count=len(scanners))
        return {"scanners": scanners}
    return plan


def fan_out(state: ScanState) -> list[Send] | str:
    if not state["scanners"]:
        return "triage"
    return [Send("run_scanner", {"path": state["path"], "scanner": name}) for name in state["scanners"]]


def run_scanner(task: ScannerTask) -> dict:
    name = task["scanner"]
    emit(stage="scanner", status="started", scanner=name)
    try:
        findings = SCANNERS[name].run(Path(task["path"]))
    except Exception as e:
        log.exception("scanner %s failed", name)
        emit(stage="scanner", status="failed", scanner=name)
        return {"failures": [ScannerFailure(scanner=name, error=type(e).__name__)]}
    emit(stage="scanner", status="ok", scanner=name, count=len(findings))
    return {"findings": findings}


def build_graph(router: LLMRouter, enabled: Collection[str] | None = None):
    """enabled: the scanners the repo owner turned on (None = all). The planner still skips irrelevant ones."""
    def triage_node(state: ScanState) -> dict:
        findings = sorted(state["findings"], key=lambda f: (f.tool, f.file, f.line, f.rule_id))
        emit(stage="triage", status="started", count=len(findings))
        try:
            issues = triage(findings, Path(state["path"]), router)
        except Exception:
            emit(stage="triage", status="failed")
            raise
        emit(stage="triage", status="ok", count=len(issues))
        return {"issues": issues}

    graph = StateGraph(ScanState)
    graph.add_node("plan", make_plan(enabled))
    graph.add_node("run_scanner", run_scanner)
    graph.add_node("triage", triage_node)
    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", fan_out, ["run_scanner", "triage"])
    graph.add_edge("run_scanner", "triage")
    graph.add_edge("triage", END)
    return graph.compile()
