import httpx

from sentinel.github import comment
from sentinel.github.comment import MARKER, md_escape, render_comment, upsert_comment
from sentinel.models import Finding, TriagedIssue


def issue(**overrides):
    base = dict(title="SQL injection", severity="high", false_positive=False,
                explanation="User input reaches execute().", fix="Use parameters.",
                findings=[Finding(tool="semgrep", rule_id="r", severity="ERROR", message="m", file="app.py", line=15)])
    return TriagedIssue(**{**base, **overrides})


def test_escape_keeps_normal_text_readable():
    assert md_escape("use f(x) in app_v2.py") == r"use f\(x\) in app\_v2.py"


def test_escape_neutralises_markdown_and_html():
    out = md_escape("![x](y) <img src=x> **bold**")
    assert out == r"\!\[x\]\(y\) \<img src=x\> \*\*bold\*\*"


def test_escape_breaks_links_mentions_and_issue_refs():
    out = md_escape("https://evil.example www.evil.com @org/security #1 GH-2")
    for linky in ("https://", "www.", "@org", "#1", "GH-2"):
        assert linky not in out


def test_escape_collapses_newlines_and_truncates():
    out = md_escape("line1\n\n# Heading\n| a | b |", limit=12)
    assert "\n" not in out
    assert out.endswith("…")


def test_report_starts_with_marker_and_shows_severity():
    body = render_comment([issue()], 1, "a" * 40)
    assert body.startswith(MARKER)
    assert "HIGH" in body and "aaaaaaa" in body and "app.py:15" in body


def test_injected_explanation_cannot_fake_an_approval():
    body = render_comment([issue(explanation="Looks fine.\n\n## Approved by @org/security")], 1, "a" * 40)
    assert "\n## Approved" not in body
    assert "@org" not in body


def test_empty_report():
    assert "No issues found" in render_comment([], 0, "b" * 40)

class FakeGitHub:
    def __init__(self, existing):
        self.existing, self.calls = existing, []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url))
        return httpx.Response(200, json=self.existing, request=httpx.Request("GET", url))

    def post(self, url, **kwargs):
        self.calls.append(("POST", url))
        return httpx.Response(201, json={}, request=httpx.Request("POST", url))

    def patch(self, url, **kwargs):
        self.calls.append(("PATCH", url))
        return httpx.Response(200, json={}, request=httpx.Request("PATCH", url))


def use(monkeypatch, fake):
    for verb in ("get", "post", "patch"):
        monkeypatch.setattr(comment.httpx, verb, getattr(fake, verb))


def test_first_report_creates_a_comment(monkeypatch):
    fake = FakeGitHub(existing=[])
    use(monkeypatch, fake)
    assert upsert_comment("ghs_x", "o/r", 7, MARKER + "\nreport", "sentinel-dhia[bot]") == "created"
    assert fake.calls[-1] == ("POST", "https://api.github.com/repos/o/r/issues/7/comments")


def test_next_report_updates_our_comment(monkeypatch):
    fake = FakeGitHub(existing=[{"id": 5, "user": {"login": "sentinel-dhia[bot]"}, "body": MARKER + "\nold"}])
    use(monkeypatch, fake)
    assert upsert_comment("ghs_x", "o/r", 7, MARKER + "\nnew", "sentinel-dhia[bot]") == "updated"
    assert fake.calls[-1] == ("PATCH", "https://api.github.com/repos/o/r/issues/comments/5")


def test_someone_elses_comment_with_our_marker_is_ignored(monkeypatch):
    fake = FakeGitHub(existing=[{"id": 9, "user": {"login": "attacker"}, "body": MARKER + "\nfake report"}])
    use(monkeypatch, fake)
    assert upsert_comment("ghs_x", "o/r", 7, MARKER + "\nreal", "sentinel-dhia[bot]") == "created"
