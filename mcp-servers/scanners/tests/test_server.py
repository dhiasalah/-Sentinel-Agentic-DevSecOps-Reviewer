import asyncio

from mcp import Client

from sentinel_scanners import server


def call(name):
    async def go():
        async with Client(server.server) as client:
            return await client.call_tool(name)
    return asyncio.run(go())


def list_tools():
    async def go():
        async with Client(server.server) as client:
            return (await client.list_tools()).tools
    return asyncio.run(go())


def test_every_scanner_is_a_read_only_tool_without_arguments():
    tools = list_tools()
    assert sorted(t.name for t in tools) == ["checkov", "gitleaks", "semgrep", "trivy"]
    for tool in tools:
        assert tool.annotations.read_only_hint and not tool.annotations.open_world_hint
        assert tool.input_schema.get("properties", {}) == {}


def test_a_tool_scans_the_root_chosen_at_start(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setenv("SENTINEL_SCAN_ROOT", str(tmp_path))
    monkeypatch.setattr(server.semgrep, "run_semgrep", lambda root: seen.append(root) or {"results": []})
    assert call("semgrep").structured_content == {"result": []}
    assert seen == [tmp_path]


def test_a_crash_is_an_error_without_the_details(monkeypatch, tmp_path):
    def boom(root):
        raise RuntimeError("docker exploded in /home/worker/secret-path")

    monkeypatch.setenv("SENTINEL_SCAN_ROOT", str(tmp_path))
    monkeypatch.setattr(server.gitleaks, "run_gitleaks", boom)
    result = call("gitleaks")
    assert result.is_error
    assert "secret-path" not in str(result.content)


def test_no_root_no_scan(monkeypatch):
    monkeypatch.delenv("SENTINEL_SCAN_ROOT", raising=False)
    assert call("trivy").is_error
