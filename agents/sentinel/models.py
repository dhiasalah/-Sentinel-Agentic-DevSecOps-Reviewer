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
