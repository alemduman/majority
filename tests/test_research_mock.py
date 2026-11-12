import json

from majority import providers
from majority.card import FactCard
from majority.research import Researcher, _int_on_page, locate


def run(env, q, options=None):
    cfg, db = env
    r = Researcher(cfg, db, providers.llm(cfg), providers.fetcher(cfg), log=lambda *a: None)
    return r.research(q, options), db


def test_trolley_card_level_a(env):
    res, db = run(env, "Вагонетка летит на пятерых. Переведёшь стрелку, чтобы погиб один?")
    assert res["status"] == "card_ready", res
    row = db.card(res["card"])
    fc = FactCard.from_dict(json.loads(row["data"]))
    assert row["level"] == "A" and fc.countries == 42 and fc.sample_size == 70000 and fc.year == 2020
    assert [o.percent for o in fc.options] == [81, 19] and fc.winner == 0
    assert "81%" in fc.fragment and fc.fetched_url.startswith("https://www.pnas.org/")
    checks = json.loads(row["checks"])
    assert all(c["ok"] for c in checks)
    assert not any(c.get("warn") for c in checks)  # 70 000, 42 и 2020 найдены на странице


def test_invented_question_gets_no_data_and_3_similar(env):
    res, db = run(env, "Какой из трёх выдуманных домов лучше?")
    assert res["status"] == "no_data"
    assert len(res["similar"]) == 3
    assert db.question(res["qid"])["status"] == "no_data"


def test_wrong_number_from_model_is_rejected(env):
    # модель «помнит» 64%, а на странице 62% → карточка не проходит, вопрос без данных
    res, db = run(env, "Чай или кофе (тест неверной цифры)")
    assert res["status"] == "no_data"
    row = db.card(res["cards"][0])
    assert row["status"] == "failed"
    assert any(not c["ok"] and "64" in c["name"] for c in json.loads(row["checks"]))


def test_country_level_b(env):
    res, db = run(env, "Чай или кофе?")
    assert res["status"] == "card_ready" and res["level"] == "B"


def test_blog_source_is_not_accepted(env):
    res, db = run(env, "Кошки или собаки?")
    assert res["status"] == "no_data"
    row = db.card(res["cards"][0])
    failed = [c["name"] for c in json.loads(row["checks"]) if not c["ok"]]
    assert "уровень не C" in failed and "формулировка охвата без «в мире»" in failed


def test_blocked_topic_never_calls_model(env):
    cfg, db = env
    llm = providers.llm(cfg)
    r = Researcher(cfg, db, llm, providers.fetcher(cfg), log=lambda *a: None)
    res = r.research("За какую партию ты на выборах?")
    assert res["status"] == "blocked" and llm.calls == []


def test_unknown_question_is_no_data_without_keys(env):
    res, _ = run(env, "Что лучше: понедельник или вторник?")
    assert res["status"] == "no_data"


def test_helpers():
    assert _int_on_page(70000, "by 70,000 participants")
    assert _int_on_page(70000, "by 70 000 participants")
    assert not _int_on_page(70000, "by 170,000 participants")
    frag, how = locate(81, "", "Switch acceptable", "In the Switch dilemma 81% agreed. Elsewhere 81 cars.")
    assert frag and "switch" in how


def test_doi_from_url():
    from majority.providers.web import WebFetcher, _blocked
    assert WebFetcher._doi("https://www.pnas.org/doi/10.1073/pnas.1911517117") == "10.1073/pnas.1911517117"
    assert WebFetcher._doi("https://example.com/x") is None
    assert _blocked("Just a moment... verify you are human")
