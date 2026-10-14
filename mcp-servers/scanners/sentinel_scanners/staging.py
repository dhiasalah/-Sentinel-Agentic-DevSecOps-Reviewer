import shutil
from pathlib import Path

CONFIG_DIR = Path(__file__).parent / "config"


def stage_config(out: Path) -> Path:
    """Copy our scanner config next to the output. Mounts come from the workspace, so config
    baked into this image is not reachable from a Kubernetes Job; copying makes it reachable."""
    staged = out / "config"
    shutil.copytree(CONFIG_DIR, staged)
    return staged
