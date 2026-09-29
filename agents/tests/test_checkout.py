import base64

import pytest

from sentinel.github.checkout import checkout_pr_head, git_env

GOOD_SHA = "eb4bc404a1b7363d84a7947b064693c873a9735c"


@pytest.mark.parametrize("repo, sha", [
    ("dhiasalah/sentinel-playground", "--upload-pack=calc.exe"),
    ("dhiasalah/sentinel-playground", "main"),
    ("evil.com/x; rm -rf /", GOOD_SHA),
    ("../../etc", GOOD_SHA),
])
def test_bad_repo_or_sha_is_refused(repo, sha):
    with pytest.raises(ValueError):
        with checkout_pr_head(repo, sha, "ghs_fake"):
            pass


def test_token_goes_in_a_github_only_header():
    env = git_env("ghs_fake")
    assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraHeader"
    assert env["GIT_CONFIG_VALUE_0"] == "Authorization: Basic " + base64.b64encode(b"x-access-token:ghs_fake").decode()
    assert env["GIT_TERMINAL_PROMPT"] == "0"
