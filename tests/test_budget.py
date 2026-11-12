import pytest

from majority.budget import Budget, BudgetExceeded, llm_cost


def test_guard_stops_before_call(env):
    cfg, db = env
    qid = db.add_question("тест бюджета")
    b = Budget(db, qid, 0.50)
    b.guard("assets", 0.30)
    b.record("assets", "mock", 0.30)
    b.guard("assets", 0.20)                 # ровно потолок — можно
    with pytest.raises(BudgetExceeded):
        b.guard("assets", 0.21)             # 0.30 + 0.21 > 0.50 — стоп
    assert abs(db.spent(qid) - 0.30) < 1e-9  # стоп не списывает деньги


def test_step_cap(env):
    cfg, db = env
    qid = db.add_question("тест лимита шага")
    b = Budget(db, qid, 0.50)
    b.record("research", "mock", 0.10)
    with pytest.raises(BudgetExceeded):
        b.guard("research", 0.03, cap=0.12)
    b.guard("render", 0.03, cap=0.12)       # другой шаг — свой лимит


def test_llm_cost_from_config_prices(env):
    cfg, _ = env
    usd = llm_cost(cfg["prices"], "gemini-2.5-flash", {"in": 1_000_000, "out": 1_000_000, "search": 1})
    p = cfg["prices"]["llm"]["gemini-2.5-flash"]
    assert abs(usd - (p["inputPer1M"] + p["outputPer1M"] + p["searchPerCall"])) < 1e-9
