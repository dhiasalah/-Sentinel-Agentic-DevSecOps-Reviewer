from collections.abc import Callable

from sentinel.config import Settings
from sentinel.github.auth import get_installation_token, load_private_key, make_app_jwt
from sentinel.github.checkout import checkout_pr_head
from sentinel.graph import build_graph
from sentinel.llm.router import build_router
from sentinel.models import RepoSettings, ScanEvent, ScannerFailure, TriagedIssue

OnEvent = Callable[[ScanEvent], None]


def scan_pr(repo: str, head_sha: str, installation_id: int, settings: Settings,
            repo_settings: RepoSettings | None = None, on_event: OnEvent | None = None,
            ) -> tuple[list[TriagedIssue], list[ScannerFailure]]:
    if settings.github_app_id is None or settings.github_private_key_path is None:
        raise RuntimeError("GITHUB_APP_ID and GITHUB_PRIVATE_KEY_PATH must be set")
    repo_settings = repo_settings or RepoSettings()
    report = on_event or (lambda event: None)
    app_jwt = make_app_jwt(settings.github_app_id, load_private_key(settings.github_private_key_path))
    token = get_installation_token(app_jwt, installation_id, repo.split("/")[1], {"contents": "read"})
    report(ScanEvent(stage="checkout", status="started"))
    with checkout_pr_head(repo, head_sha, token) as path:
        report(ScanEvent(stage="checkout", status="ok"))
        graph = build_graph(build_router(settings, repo_settings.llm_order), enabled=repo_settings.scanners)
        result = {}
        # "custom" carries the nodes' progress events, "values" the state after each step (the last one is the result).
        for mode, chunk in graph.stream({"path": str(path)}, stream_mode=["custom", "values"]):
            if mode == "custom":
                report(chunk)
            else:
                result = chunk
    return result["issues"], result["failures"]
