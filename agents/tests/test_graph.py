import time

import pytest

from sentinel import graph
from sentinel.models import Finding


def finding(tool, line):
    return Finding(tool=tool, rule_id="r", severity="ERROR", message="m", file="app.py", line=line)


def slow_scanner(tool, line):
    def scan(path):
        time.sleep(0.5)
        return [finding(tool, line)]
    return scan


@pytest.fixture
def seen(monkeypatch):
    calls = []

    def fake_triage(findings, root, router):
        calls.append(findings)
        return []

    monkeypatch.setattr(graph, "triage", fake_triage)
    return calls


def test_all_scanners_run_in_parallel_and_triage_sees_every_finding_once(monkeypatch, seen):
    monkeypatch.setattr(graph, "SCANNERS", {"b": slow_scanner("b", 2), "a": slow_scanner("a", 1)})
    start = time.perf_counter()
    result = graph.build_graph(router=None).invoke({"path": "."})
    assert time.perf_counter() - start < 0.9
    assert result["scanners"] == ["a", "b"]
    assert len(seen) == 1
    assert [f.tool for f in seen[0]] == ["a", "b"]


def test_a_crashing_scanner_fails_the_whole_scan(monkeypatch, seen):
    def boom(path):
        raise RuntimeError("scanner exploded")

    monkeypatch.setattr(graph, "SCANNERS", {"ok": slow_scanner("ok", 1), "bad": boom})
    with pytest.raises(RuntimeError, match="scanner exploded"):
        graph.build_graph(router=None).invoke({"path": "."})
    assert seen == []
