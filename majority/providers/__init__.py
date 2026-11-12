"""Выбор провайдеров: без ключей (или MAJORITY_MOCK=1) — mock, иначе настоящие."""


def llm(cfg):
    if cfg.get("mock"):
        from .mock import MockLLM
        return MockLLM()
    from .gemini import GeminiLLM
    return GeminiLLM(cfg)


def fetcher(cfg, log=print):
    if cfg.get("mock"):
        from .mock import MockFetcher
        return MockFetcher()
    from .web import WebFetcher
    return WebFetcher(log=log)
