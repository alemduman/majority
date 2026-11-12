"""Gemini: текст с поиском Google (grounding). Ключ — только из переменной окружения GEMINI_API_KEY."""
import json
import os
import time
import urllib.error
import urllib.request

from ..budget import llm_cost
from .base import LLMResult
from .web import resolve_redirect

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiLLM:
    name = "gemini"

    def __init__(self, cfg):
        self.key = os.environ.get("GEMINI_API_KEY", "")
        if not self.key:
            raise RuntimeError("нет GEMINI_API_KEY в окружении")
        self.model = cfg.get("llmModel", "gemini-2.5-flash")
        self.prices = cfg["prices"]
        self.expected_out = cfg.get("research", {}).get("expectedOutTokens", 6000)

    def estimate(self, prompt, search=False):
        tokens_in = len(prompt) / 3.2 + (2500 if search else 0)  # с поиском в запрос добавляются найденные сниппеты
        return llm_cost(self.prices, self.model, {"in": tokens_in, "out": self.expected_out, "search": 1 if search else 0})

    def generate(self, prompt, search=False, temperature=0.2):
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": temperature}}
        if search:
            body["tools"] = [{"google_search": {}}]
        data = json.dumps(body).encode()
        last = None
        for attempt in range(3):
            req = urllib.request.Request(API.format(model=self.model), data=data, method="POST",
                                         headers={"Content-Type": "application/json", "x-goog-api-key": self.key})
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    resp = json.loads(r.read())
                break
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}: {e.read()[:300].decode(errors='replace')}"
                if e.code in (429, 500, 503) and attempt < 2:
                    time.sleep(8 * (attempt + 1))
                    continue
                raise RuntimeError("Gemini: " + last) from None
        else:
            raise RuntimeError("Gemini: " + str(last))
        cand = (resp.get("candidates") or [{}])[0]
        text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []) if not p.get("thought"))
        um = resp.get("usageMetadata", {})
        gm = cand.get("groundingMetadata", {}) or {}
        usage = {"in": um.get("promptTokenCount", 0) + um.get("toolUsePromptTokenCount", 0),
                 "out": um.get("candidatesTokenCount", 0) + um.get("thoughtsTokenCount", 0),
                 "search": 1 if (search and gm.get("webSearchQueries")) else 0}
        sources = []
        for ch in gm.get("groundingChunks", []) or []:
            w = ch.get("web") or {}
            if w.get("uri"):
                sources.append({"url": resolve_redirect(w["uri"]), "title": w.get("title", "")})
        return LLMResult(text=text, usage=usage, sources=sources, model=self.model)

    def cost(self, usage):
        return llm_cost(self.prices, self.model, usage)
