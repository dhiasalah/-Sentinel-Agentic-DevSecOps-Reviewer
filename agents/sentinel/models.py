from pydantic import BaseModel
from typing import Literal

class Finding(BaseModel):
    tool: str
    rule_id: str
    severity: str
    message: str
    file: str
    line: int
    cwe: list[str] = []
    end_line: int | None = None


Severity = Literal["critical", "high", "medium", "low", "info"]


class TriagedIssue(BaseModel):
    title: str
    severity: Severity
    false_positive: bool
    explanation: str
    fix: str
    findings: list[Finding]
    review_reasons: list[str] = []

class ScannerFailure(BaseModel):
    scanner: str
    error: str


class ScanEvent(BaseModel):
    """One step of a scan, shown live in the dashboard. Structured on purpose: no free text."""
    stage: Literal["checkout", "plan", "scanner", "triage", "report"]
    status: Literal["started", "ok", "failed", "skipped"]
    scanner: str | None = None
    count: int | None = None


ScannerName = Literal["gitleaks", "semgrep", "trivy", "checkov"]


class RepoSettings(BaseModel):
    """Chosen by the repo owner in the dashboard. The defaults are the most thorough choice."""
    scanners: list[ScannerName] = ["gitleaks", "semgrep", "trivy", "checkov"]
    report_min_severity: Severity = "info"
    llm_order: list[Literal["gemini", "groq"]] = ["gemini", "groq"]
