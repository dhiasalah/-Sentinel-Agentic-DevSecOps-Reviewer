import asyncio
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters
from mcp.client.stdio import get_default_environment
from mcp.types import CallToolResult

from sentinel.models import Finding

SERVER_DIR = Path(__file__).resolve().parents[2] / "mcp-servers" / "scanners"
MAX_FINDINGS = 500
TIMEOUT = 900


def server_params(path: Path) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "sentinel_scanners.server"],
        cwd=SERVER_DIR,
        env={**get_default_environment(), "SENTINEL_SCAN_ROOT": str(path.resolve())},
    )


def to_findings(name: str, result: CallToolResult) -> list[Finding]:
    if result.is_error or result.structured_content is None:
        raise RuntimeError(f"MCP tool {name} failed: {result.content}")
    items = result.structured_content["result"]
    if len(items) > MAX_FINDINGS:
        raise RuntimeError(f"MCP tool {name} returned {len(items)} findings (limit {MAX_FINDINGS})")
    findings = [Finding.model_validate(item) for item in items]
    if any(f.tool != name for f in findings):
        raise RuntimeError(f"MCP tool {name} returned findings for another tool")
    return findings


async def _call(name: str, path: Path) -> list[Finding]:
    async with Client(server_params(path), read_timeout_seconds=TIMEOUT) as client:
        return to_findings(name, await client.call_tool(name))


def call_scanner(name: str, path: Path) -> list[Finding]:
    return asyncio.run(_call(name, path))
