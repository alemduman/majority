"""Ограничитель бюджета: прогноз перед каждым платным вызовом и журнал расходов по роликам и шагам."""


class BudgetExceeded(Exception):
    pass


class Budget:
    def __init__(self, db, qid, ceiling):
        self.db, self.qid, self.ceiling = db, qid, float(ceiling)

    @property
    def spent(self):
        return self.db.spent(self.qid)

    def guard(self, step, forecast_usd, what="", cap=None):
        """Вызывать ДО платного вызова. Останавливает конвейер, если прогноз + потраченное > потолка ролика
        (или > отдельного лимита шага cap)."""
        if cap is not None:
            done = self.db.spent(self.qid, step)
            if done + float(forecast_usd) > float(cap) + 1e-9:
                raise BudgetExceeded(
                    f"Стоп: шаг «{step}» ({what}) обойдётся примерно в ${forecast_usd:.3f}, на этот шаг уже потрачено "
                    f"${done:.3f}, лимит шага ${float(cap):.2f}. Ничего не вызвано.")
        total = self.spent + float(forecast_usd)
        if total > self.ceiling + 1e-9:
            raise BudgetExceeded(
                f"Стоп: шаг «{step}» ({what}) обойдётся примерно в ${forecast_usd:.3f}, уже потрачено ${self.spent:.3f}, "
                f"вместе ${total:.3f} — это больше потолка ${self.ceiling:.2f} на ролик. Ничего не вызвано.")
        return total

    def record(self, step, provider, usd, note=""):
        self.db.add_cost(self.qid, step, provider, usd, note)


def llm_cost(prices, model, usage):
    """usage: {"in": токены, "out": токены, "search": число поисковых запросов}."""
    p = (prices.get("llm") or {}).get(model) or {}
    return (usage.get("in", 0) * p.get("inputPer1M", 0) + usage.get("out", 0) * p.get("outputPer1M", 0)) / 1e6 + \
        usage.get("search", 0) * p.get("searchPerCall", 0)
