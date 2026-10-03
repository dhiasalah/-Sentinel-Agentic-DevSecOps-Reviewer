import operator
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from sentinel.llm.router import LLMRouter
from sentinel.models import Finding, TriagedIssue
from sentinel.scanners import gitleaks, semgrep
from sentinel.triage import triage

Scanner = Callable[[Path], list[Finding]]

SCANNERS: dict[str, Scanner] = {
    "gitleaks": lambda path: gitleaks.parse_findings(gitleaks.run_gitleaks(path)),
    "semgrep": lambda path: semgrep.parse_findings(semgrep.run_semgrep(path)),
}


class ScanState(TypedDict):
    path: str
    scanners: list[str]
    findings: Annotated[list[Finding], operator.add]
    issues: list[TriagedIssue]


class ScannerTask(TypedDict):
    path: str
    scanner: str

def plan(state: ScanState) -> dict:
    return {"scanners": sorted(SCANNERS)}


def fan_out(state: ScanState) -> list[Send]:
    return [Send("run_scanner", {"path": state["path"], "scanner": name}) for name in state["scanners"]]


def run_scanner(task: ScannerTask) -> dict:
    return {"findings": SCANNERS[task["scanner"]](Path(task["path"]))}

def build_graph(router: LLMRouter):
    def triage_node(state: ScanState) -> dict:
        findings = sorted(state["findings"], key=lambda f: (f.tool, f.file, f.line, f.rule_id))
        return {"issues": triage(findings, Path(state["path"]), router)}

    graph = StateGraph(ScanState)
    graph.add_node("plan", plan)
    graph.add_node("run_scanner", run_scanner)
    graph.add_node("triage", triage_node)
    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", fan_out, ["run_scanner"])
    graph.add_edge("run_scanner", "triage")
    graph.add_edge("triage", END)
    return graph.compile()
