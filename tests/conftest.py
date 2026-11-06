import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "baselines"))

from europress_data.config import load_config  # noqa: E402
from europress_data.generate import generate  # noqa: E402

SMALL = {"target_devices": 60, "holdout_org_fraction": 0.2, "private_decision_cutoff": "2026-08-16"}


def make(tmp, seed=20261023, **ov):
    cfg = load_config("quickstart", seed, tmp, {**SMALL, **ov})
    generate(cfg, workers=1, verbose=False)
    return Path(tmp)


@pytest.fixture(scope="session")
def small_dataset(tmp_path_factory):
    return make(tmp_path_factory.mktemp("small") / "ds")


@pytest.fixture()
def mutable_copy(small_dataset, tmp_path):
    dst = tmp_path / "copy"
    shutil.copytree(small_dataset, dst)
    return dst
