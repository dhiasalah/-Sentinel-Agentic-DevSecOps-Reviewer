from sentinel.config import Settings
from sentinel.github.auth import get_installation_token, load_private_key, make_app_jwt
from sentinel.github.checkout import checkout_pr_head
from sentinel.graph import build_graph
from sentinel.llm.router import build_router
from sentinel.models import ScannerFailure, TriagedIssue


def scan_pr(repo: str, head_sha: str, installation_id: int, settings: Settings
            ) -> tuple[list[TriagedIssue], list[ScannerFailure]]:
    if settings.github_app_id is None or settings.github_private_key_path is None:
        raise RuntimeError("GITHUB_APP_ID and GITHUB_PRIVATE_KEY_PATH must be set")
    app_jwt = make_app_jwt(settings.github_app_id, load_private_key(settings.github_private_key_path))
    token = get_installation_token(app_jwt, installation_id, repo.split("/")[1], {"contents": "read"})
    with checkout_pr_head(repo, head_sha, token) as path:
        result = build_graph(build_router(settings)).invoke({"path": str(path)})
    return result["issues"], result["failures"]

