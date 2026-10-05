import json

import pytest

from sentinel.llm.providers import ProviderUnavailable
from sentinel.llm.router import AllProvidersFailed, LLMResponse, LLMRouter
from sentinel.models import Finding
from sentinel.triage import BATCH_SIZE, TriageError, batches, build_prompt, parse_response, read_snippet, triage


def make_finding(line=2, rule="sqli", severity="ERROR"):
    return Finding(tool="semgrep", rule_id=rule, severity=severity, message="msg", file="app.py", line=line)


def issue(ids, severity="high"):
    return {"finding_ids": ids, "title": "t", "severity": severity,
            "false_positive": False, "explanation": "e", "fix": "f"}


def answer(*issues):
    return json.dumps({"issues": list(issues)})


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "app.py").write_text("a = 1\nquery = f'SELECT {x}'\nb = 2\n")
    return tmp_path


class FakeRouter:
    def __init__(self, text):
        self.text = text
        self.json_mode = None

    def complete(self, system, user, json_mode=False, check=None):
        self.json_mode = json_mode
        return LLMResponse(provider="fake", text=self.text)


class Provider:
    def __init__(self, name, text):
        self.name, self.text = name, text

    def complete(self, system, user, json_mode=False):
        return self.text


def test_merges_duplicate_findings_into_one_issue():
    findings = [make_finding(rule="sqli-a"), make_finding(rule="sqli-b")]
    issues = parse_response(answer(issue([1, 2])), findings)
    assert len(issues) == 1
    assert issues[0].findings == findings


def test_rejects_invented_finding_id():
    with pytest.raises(TriageError, match="unknown"):
        parse_response(answer(issue([1, 99])), [make_finding()])


def test_rejects_dropped_finding():
    with pytest.raises(TriageError, match="dropped"):
        parse_response(answer(issue([1])), [make_finding(), make_finding()])


def test_rejects_prose_instead_of_json():
    with pytest.raises(TriageError):
        parse_response("Sure! Here is the triage you asked for.", [make_finding()])


def test_snippet_refuses_paths_outside_repo(repo):
    with pytest.raises(ValueError):
        read_snippet(repo, "../outside.txt", 1)


def test_code_is_wrapped_as_untrusted(repo):
    prompt = build_prompt([make_finding()], repo, tag="abc123")
    inside = prompt.split("<untrusted-abc123>")[1].split("</untrusted-abc123>")[0]
    assert "SELECT" in inside
    assert "app.py:2" in inside


def test_triage_asks_for_json_and_sorts_by_severity(repo):
    router = FakeRouter(answer(issue([1], "low"), issue([2], "critical")))
    issues = triage([make_finding(1, severity="INFO"), make_finding(3)], repo, router)
    assert router.json_mode is True
    assert [i.severity for i in issues] == ["critical", "low"]

def test_hijacked_llm_cannot_hide_a_real_finding(repo):
    hijacked = answer({**issue([1], severity="info"), "false_positive": True})
    issues = triage([make_finding(line=2)], repo, FakeRouter(hijacked))
    assert issues[0].severity == "high"
    assert issues[0].review_reasons

def test_secret_lines_never_reach_the_llm(tmp_path):
    (tmp_path / "app.py").write_text('a = 1\nTOKEN = "hunter2hunter2"\nquery = f"SELECT {x}"\n')
    leak = Finding(tool="gitleaks", rule_id="secret", severity="ERROR", message="m",
                   file="app.py", line=2, end_line=2)
    prompt = build_prompt([leak, make_finding(line=3)], tmp_path, tag="abc123")
    assert "hunter2" not in prompt
    assert "SELECT" in prompt


def test_an_answer_that_drops_a_finding_gets_a_second_opinion(repo):
    router = LLMRouter([Provider("gemini", answer(issue([1]))), Provider("groq", answer(issue([1, 2])))])
    [only] = triage([make_finding(1), make_finding(3)], repo, router)
    assert len(only.findings) == 2


def finding_in(file, line=1, tool="semgrep"):
    return Finding(tool=tool, rule_id="r", severity="ERROR", message="m", file=file, line=line)


def test_batches_are_small_and_keep_each_file_together():
    findings = [finding_in("a.py", n) for n in range(3)] + [finding_in("b.py", n) for n in range(6)]
    assert [[f.file for f in b] for b in batches(findings)] == [["a.py"] * 3, ["b.py"] * 6]


def test_a_huge_file_is_split_and_nothing_is_lost():
    findings = [finding_in("a.py", n) for n in range(BATCH_SIZE * 2 + 1)]
    result = batches(findings)
    assert all(len(b) <= BATCH_SIZE for b in result)
    assert [f for b in result for f in b] == findings


def test_secrets_stay_hidden_when_the_leak_is_in_another_batch(tmp_path):
    (tmp_path / "app.py").write_text('a = 1\nTOKEN = "hunter2hunter2"\nquery = f"SELECT {x}"\n')
    leak = Finding(tool="gitleaks", rule_id="secret", severity="ERROR", message="m",
                   file="app.py", line=2, end_line=2)
    other = make_finding(line=3)
    prompt = build_prompt([other], tmp_path, tag="abc123", hide_from=[leak, other])
    assert "hunter2" not in prompt


class CountingRouter:
    def __init__(self):
        self.calls = 0

    def complete(self, system, user, json_mode=False, check=None):
        self.calls += 1
        count = user.count("Finding ")
        return LLMResponse(provider="fake", text=answer(*(issue([i]) for i in range(1, count + 1))))


def test_big_scans_are_triaged_batch_by_batch(tmp_path):
    for name in ("a.py", "b.py"):
        (tmp_path / name).write_text("x = 1\n" * 20)
    findings = [finding_in(name, n) for name in ("a.py", "b.py") for n in range(1, 11)]
    router = CountingRouter()
    issues = triage(findings, tmp_path, router)
    assert router.calls == 4
    assert sorted((f.file, f.line) for i in issues for f in i.findings) == sorted((f.file, f.line) for f in findings)




class Unavailable:
    name = "gemini"

    def __init__(self, failures):
        self.failures = failures

    def complete(self, system, user, json_mode=False):
        if self.failures:
            self.failures -= 1
            raise ProviderUnavailable("429")
        return answer(issue([1]))


def test_out_of_quota_waits_then_retries(repo, monkeypatch):
    waits = []
    monkeypatch.setattr("sentinel.triage.time.sleep", waits.append)
    [only] = triage([make_finding()], repo, LLMRouter([Unavailable(failures=2)]))
    assert waits == [30, 60] and len(only.findings) == 1


def test_gives_up_after_the_last_wait(repo, monkeypatch):
    monkeypatch.setattr("sentinel.triage.time.sleep", lambda s: None)
    with pytest.raises(AllProvidersFailed):
        triage([make_finding()], repo, LLMRouter([Unavailable(failures=3)]))
