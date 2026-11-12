import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("MAJORITY_MOCK", "1")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("MAJORITY_DB", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("MAJORITY_OUT", str(tmp_path / "output"))
    monkeypatch.setenv("MAJORITY_PAGES", str(tmp_path / "pages"))
    from majority import config
    from majority.db import DB
    cfg = config.load()
    return cfg, DB(config.db_path())
