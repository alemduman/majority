"""Mock-провайдеры: весь конвейер работает без ключей и без сети. Ответы берутся из tests/fixtures."""
import json
import re
from pathlib import Path

from ..config import ROOT
from .base import LLMResult

FIX = ROOT / "tests" / "fixtures"


class MockLLM:
    """Отвечает заготовками: fixtures/llm/*.json, у каждой поле "match" — регулярка по тексту запроса."""
    name = "mock"

    def __init__(self, fixtures=FIX):
        self.items = []
        for f in sorted((Path(fixtures) / "llm").glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            self.items.append(d)
        self.calls = []

    def estimate(self, prompt, search=False):
        return 0.0

    def cost(self, usage):
        return 0.0

    def generate(self, prompt, search=False, temperature=0.2):
        self.calls.append({"prompt": prompt[:200], "search": search})
        kind = "extract" if "PAGE TEXT:" in prompt else "similar" if "has no primary survey data" in prompt else "search"
        for d in self.items:
            if d.get("kind", "search") == kind and re.search(d["match"], prompt, re.I | re.S):
                resp = d["response"]
                return LLMResult(text="```json\n" + json.dumps(resp, ensure_ascii=False) + "\n```",
                                 usage={"in": len(prompt) // 3, "out": 500, "search": int(search)},
                                 sources=[{"url": u, "title": ""} for u in d.get("sources", [])], model="mock")
        empty = {"found": False, "candidates": [], "similar": []} if kind == "search" else {"similar": []} \
            if kind == "similar" else {"options": []}
        return LLMResult(text="```json\n" + json.dumps(empty) + "\n```", usage={}, model="mock")


class MockFetcher:
    """URL → файл из fixtures/pages по таблице fixtures/pages/index.json."""
    name = "mock-web"

    def __init__(self, fixtures=FIX):
        self.dir = Path(fixtures) / "pages"
        p = self.dir / "index.json"
        self.index = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def fetch(self, url):
        from .. import textutil
        name = self.index.get(url)
        if not name:
            raise RuntimeError(f"mock: нет страницы для {url}")
        return url, textutil.html_to_text((self.dir / name).read_text(encoding="utf-8"))


class MockImages:
    name = "mock"

    def generate(self, prompt, out_path, ref=None):
        from PIL import Image, ImageDraw
        import zlib
        h = zlib.crc32(prompt.encode())
        c1 = ((h >> 16) & 255, (h >> 8) & 255, h & 255)
        im = Image.new("RGB", (1080, 1920), c1)
        d = ImageDraw.Draw(im)
        for i in range(0, 1920, 120):
            d.rectangle([0, i, 1080, i + 60], fill=tuple(min(255, x + 25) for x in c1))
        im.save(out_path)


class MockTTS:
    name = "mock"

    def synth(self, text, out_wav, seconds=None):
        import wave
        import struct
        dur = seconds or max(0.8, len(text) / 15)
        with wave.open(out_wav, "w") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(struct.pack("<h", 0) * int(24000 * dur))
        return {"seconds": dur}


class MockPublisher:
    name = "dry-run"

    def publish(self, video_path, caption, ai_generated=True):
        return "dry-run:" + Path(video_path).name
