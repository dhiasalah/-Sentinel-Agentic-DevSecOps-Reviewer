import re

from sentinel.models import Severity, TriagedIssue

SEVERITY_ORDER: list[Severity] = ["critical", "high", "medium", "low", "info"]
SCANNER_FLOOR: dict[str, Severity] = {"ERROR": "high", "WARNING": "medium", "INFO": "low"}

INJECTION_PATTERN = re.compile(
    r"ignore (all |any )?(previous|prior|above)"
    r"|false[ _-]?positive"
    r"|\b(ai|llm|assistant|chatgpt|gemini|reviewer)s?\b"
    r"|</?untrusted"
    r"|^\s*#?\s*system\s*:",
    re.IGNORECASE | re.MULTILINE,
)


def rank(severity: Severity) -> int:
    return SEVERITY_ORDER.index(severity)


def scanner_floor(issue: TriagedIssue) -> Severity:
    floors = [SCANNER_FLOOR.get(f.severity.upper(), "high") for f in issue.findings]
    return min(floors, key=rank)


def looks_like_injection(text: str) -> bool:
    return bool(INJECTION_PATTERN.search(text))


def apply_policy(issue: TriagedIssue, snippets: list[str]) -> TriagedIssue:
    reasons = []
    severity = issue.severity
    floor = scanner_floor(issue)
    if rank(severity) > rank(floor):
        reasons.append(f"AI lowered severity to {severity}; scanner floor is {floor}")
        severity = floor
    if issue.false_positive:
        reasons.append("AI marked it as a false positive")
    if any(looks_like_injection(s) for s in snippets):
        reasons.append("code near this finding addresses the AI (possible prompt injection)")
    return issue.model_copy(update={"severity": severity, "review_reasons": reasons})
