"""Конфиг приложения: config.json в корне репозитория + переменные окружения (ключи только оттуда)."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULTS = {
    "language": "ru",
    "voice": {"engine": "gemini", "name": "Charon"},
    "font": "fonts/Montserrat-Black.ttf",
    "colors": {"bg": "#0E1020", "accent": "#FFD93B", "text": "#FFFFFF", "bar": "#3DDC97", "barOther": "#5A6275"},
    "durations": {"question": 2.0, "option": 2.5, "countdown": 2.0, "reveal": 5.0, "outro": 2.0},
    "budget": {"ceilingUsd": 0.50, "targetUsd": 0.30, "maxRegenerationsPerImage": 2},
    "approvalMode": "manual",
    "prices": {
        "llm": {"gemini-2.5-flash": {"inputPer1M": 0.30, "outputPer1M": 2.50, "searchPerCall": 0.035}},
        "imagePerUnit": {"gemini-2.5-flash-image": 0.039},
        "ttsPer1000Chars": {"gemini": 0.02, "edge": 0.0, "mock": 0.0},
        "videoPerSecond": {"none": 0.0},
    },
    "llmModel": "gemini-2.5-flash",
    # исследование: сколько кандидатов-источников проверять и бюджет на один вопрос
    "research": {"maxCandidates": 4, "maxPageChars": 60000, "budgetUsd": 0.12, "conflictPolicy": "C",
                 "expectedOutTokens": 6000},
    "primarySources": ["yougov.com", "today.yougov.com", "business.yougov.com", "pewresearch.org", "ipsos.com", "gallup.com",
                        "news.gallup.com", "pnas.org", "nature.com", "science.org", "sciencedirect.com", "springer.com",
                        "wiley.com", "plos.org", "ncbi.nlm.nih.gov", "europepmc.org", "statista.com", "gfk.com", "nim.org",
                        "oecd.org", "europa.eu", "who.int", "worldvaluessurvey.org", "doi.org", "jstor.org", "cambridge.org",
                        "oup.com", "ebi.ac.uk", "sagepub.com", "tandfonline.com", "frontiersin.org", "mdpi.com", "arxiv.org", "osf.io"],
    # темы под запретом (политика, религия, медицина, трагедии, 18+): регулярные выражения, проверяются по началу слова
    "blockedTopics": [r"политик", r"выбор(?:ы|ах|ов)\b", r"парти[яи]", r"президент", r"религи", r"\bбог", r"церк", r"мечет",
                       r"болезн", r"лекарств", r"вакцин", r"медиц", r"смерт", r"убийств", r"теракт", r"катастроф", r"войн",
                       r"секс", r"алкогол", r"наркот", r"politic", r"election", r"religio", r"\bgod\b", r"vaccin", r"disease",
                       r"medic", r"\bdrug", r"\bsex", r"terror", r"\bwar\b"],
}


def _merge(a, b):
    out = dict(a)
    for k, v in (b or {}).items():
        out[k] = _merge(a[k], v) if isinstance(v, dict) and isinstance(a.get(k), dict) else v
    return out


def load(path=None):
    p = Path(path) if path else ROOT / "config.json"
    user = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    cfg = _merge(DEFAULTS, user)
    cfg["mock"] = os.environ.get("MAJORITY_MOCK", "") == "1" or not os.environ.get("GEMINI_API_KEY")
    if os.environ.get("MAJORITY_PAGES"):
        cfg["pagesDir"] = os.environ["MAJORITY_PAGES"]
    return cfg


def db_path():
    return Path(os.environ.get("MAJORITY_DB") or ROOT / "data" / "majority.sqlite")
