import asyncio

import pytest
from mcp import Client
from mcp.types import CallToolResult, TextContent

from sentinel import mcp_scanners
from sentinel.mcp_scanners import server_params, to_findings

FINDING = {"tool": "semgrep", "rule_id": "r", "severity": "ERROR", "message": "m", "file": "a.py", "line": 3}


def result(items=None, error=False):
    text = "Error executing tool semgrep" if error else ""
    return CallToolResult(content=[TextContent(type="text", text=text)], is_error=error,
                          structured_content=None if error else {"result": items})


def test_tool_output_becomes_findings():
    [finding] = to_findings("semgrep", result([FINDING]))
    assert (finding.tool, finding.file, finding.line) == ("semgrep", "a.py", 3)


@pytest.mark.parametrize("bad", [
    result(error=True),
    result([{**FINDING, "line": "three"}]),
    result([FINDING] * (mcp_scanners.MAX_FINDINGS + 1)),
    result([{**FINDING, "tool": "gitleaks"}]),
], ids=["error", "bad-schema", "flood", "wrong-tool"])
def test_bad_tool_output_is_refused(bad):
    with pytest.raises((RuntimeError, ValueError)):
        to_findings("semgrep", bad)


def test_server_gets_the_repo_but_not_our_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "sk-test")
    params = server_params(tmp_path)
    assert params.env["SENTINEL_SCAN_ROOT"] == str(tmp_path.resolve())
    assert "GEMINI_API_KEY" not in params.env


def test_server_starts_over_stdio_and_offers_every_scanner(tmp_path):
    async def tool_names():
        async with Client(server_params(tmp_path)) as client:
            return sorted(t.name for t in (await client.list_tools()).tools)

    assert asyncio.run(tool_names()) == ["checkov", "gitleaks", "semgrep", "trivy"]
