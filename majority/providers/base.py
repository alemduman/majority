"""Интерфейсы провайдеров. У каждого есть mock-реализация (providers/mock.py), чтобы конвейер работал без ключей."""
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class LLMResult:
    text: str
    usage: dict = field(default_factory=dict)          # {"in": ..., "out": ..., "search": ...}
    sources: list = field(default_factory=list)        # [{"url": ..., "title": ...}] — ссылки, найденные поиском
    model: str = ""


class LLMProvider(Protocol):
    name: str

    def generate(self, prompt: str, search: bool = False) -> LLMResult: ...

    def estimate(self, prompt: str, search: bool = False) -> float: ...


class SearchProvider(Protocol):
    """Находит первоисточники для вопроса. Возвращает кандидатов (JSON-подобные словари) + сами ссылки поиска."""
    name: str

    def find_sources(self, question: str, options: list | None) -> LLMResult: ...


class Fetcher(Protocol):
    """Открывает страницу и возвращает (итоговый URL, текст)."""
    name: str

    def fetch(self, url: str) -> tuple[str, str]: ...


class ImageProvider(Protocol):
    name: str

    def generate(self, prompt: str, out_path: str, ref: bytes | None = None) -> None: ...


class TTSProvider(Protocol):
    name: str

    def synth(self, text: str, out_wav: str) -> dict: ...


class VideoProvider(Protocol):
    name: str

    def clip(self, prompt: str, seconds: float, out_path: str) -> None: ...


class Publisher(Protocol):
    name: str

    def publish(self, video_path: str, caption: str, ai_generated: bool = True) -> str: ...
