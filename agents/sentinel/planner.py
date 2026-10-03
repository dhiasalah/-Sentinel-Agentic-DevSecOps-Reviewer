import fnmatch
import os
from pathlib import Path

MAX_FILES = 20_000


def _fail(error: OSError) -> None:
    raise error


def list_files(root: Path, limit: int = MAX_FILES) -> list[str] | None:
    names = []
    try:
        for _, dirnames, filenames in os.walk(root, onerror=_fail):
            dirnames[:] = [d for d in dirnames if d != ".git"]
            names += filenames
            if len(names) > limit:
                return None
    except OSError:
        return None
    return names

def choose_scanners(triggers: dict[str, tuple[str, ...]], files: list[str] | None) -> list[str]:
    if files is None:
        return sorted(triggers)
    names = [f.lower() for f in files]
    return sorted(
        scanner
        for scanner, patterns in triggers.items()
        if any(fnmatch.fnmatchcase(name, p) for name in names for p in patterns)
    )
