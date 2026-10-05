import time

import pytest

from sentinel import graph
from sentinel.models import Finding, ScannerFailure

def finding(tool, line):
    return Finding(tool=tool, rule_id="r", severity="ERROR", message="m", file="app.py", line=line)

def everywhere(run):
    return graph.ScannerSpec(run=run, files=("*",))

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
    monkeypatch.setattr(graph, "SCANNERS", {"b": everywhere(slow_scanner("b", 2)), "a": everywhere(slow_scanner("a", 1))})
    start = time.perf_counter()
    result = graph.build_graph(router=None).invoke({"path": "."})
    assert time.perf_counter() - start < 0.9
    assert result["scanners"] == ["a", "b"]
    assert len(seen) == 1
    assert [f.tool for f in seen[0]] == ["a", "b"]


def test_a_crashing_scanner_is_reported_and_the_others_still_count(monkeypatch, seen):
    def boom(path):
        raise RuntimeError("scanner exploded in /tmp/secret-path")

    monkeypatch.setattr(graph, "SCANNERS", {"ok": everywhere(slow_scanner("ok", 1)), "bad": everywhere(boom)})
    result = graph.build_graph(router=None).invoke({"path": "."})
    assert [f.tool for f in seen[0]] == ["ok"]
    assert result["failures"] == [ScannerFailure(scanner="bad", error="RuntimeError")]
    assert "secret-path" not in result["failures"][0].model_dump_json()

    
def test_nothing_to_scan_still_reaches_triage(monkeypatch, seen, tmp_path):
    (tmp_path / "README.md").write_text("docs only")
    python_only = graph.ScannerSpec(run=slow_scanner("py", 1), files=("*.py",))
    monkeypatch.setattr(graph, "SCANNERS", {"py": python_only})
    result = graph.build_graph(router=None).invoke({"path": str(tmp_path)})
    assert result["scanners"] == []
    assert result["issues"] == []
    assert seen == [[]]


def events_of(compiled, path="."):
    stream = compiled.stream({"path": path}, stream_mode=["custom", "values"])
    return [chunk for mode, chunk in stream if mode == "custom"]


def test_progress_events_follow_the_run(monkeypatch, seen):
    def boom(path):
        raise RuntimeError("down")

    monkeypatch.setattr(graph, "SCANNERS", {"ok": everywhere(slow_scanner("ok", 1)), "bad": everywhere(boom)})
    events = [(e.stage, e.status, e.scanner, e.count) for e in events_of(graph.build_graph(router=None))]
    assert events[0] == ("plan", "ok", None, 2)
    assert ("scanner", "ok", "ok", 1) in events and ("scanner", "failed", "bad", None) in events
    assert events[-2:] == [("triage", "started", None, 1), ("triage", "ok", None, 0)]


def test_scanners_turned_off_by_the_owner_are_skipped_and_reported(monkeypatch, seen):
    monkeypatch.setattr(graph, "SCANNERS", {"a": everywhere(slow_scanner("a", 1)), "b": everywhere(slow_scanner("b", 2))})
    events = [(e.stage, e.status, e.scanner) for e in events_of(graph.build_graph(router=None, enabled=["a"]))]
    assert ("scanner", "skipped", "b") in events and ("scanner", "started", "b") not in events
    assert [f.tool for f in seen[0]] == ["a"]


def test_a_triage_crash_is_reported_then_raised(monkeypatch):
    def broken(findings, root, router):
        raise RuntimeError("all providers failed")

    monkeypatch.setattr(graph, "triage", broken)
    monkeypatch.setattr(graph, "SCANNERS", {"a": everywhere(slow_scanner("a", 1))})
    events = []
    with pytest.raises(RuntimeError):
        for chunk in graph.build_graph(router=None).stream({"path": "."}, stream_mode="custom"):
            events.append((chunk.stage, chunk.status))
    assert events[-1] == ("triage", "failed")
