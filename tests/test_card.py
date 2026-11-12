from majority import card as C
from majority import textutil

PRIMARY = ["pnas.org", "yougov.com"]
FRAG = "sacrificing one person to save five was considered acceptable in the Switch dilemma by 81% of participants on average"


def make(**kw):
    d = dict(question="q", options=[C.Option("Перевести", 81, "Switch"), C.Option("Не вмешиваться", 19, "no", "complement")],
             organization="Awad et al.", year=2020, sample_size=70000, countries=42, scope="42 страны",
             survey_wording="w", metric="single", source_url="https://www.pnas.org/doi/x", fetched_url="https://www.pnas.org/doi/x",
             fragment=FRAG, source_short="PNAS, 42 страны, 2020")
    d.update(kw)
    return C.FactCard(**d)


def names_failed(card):
    ok, res = C.check(card, PRIMARY)
    return ok, [r["name"] for r in res if not r["ok"]]


def test_good_card_passes_level_a():
    ok, failed = names_failed(make())
    assert ok, failed
    assert C.level_for(make(), PRIMARY) == "A"


def test_number_must_be_in_fragment():
    ok, failed = names_failed(make(options=[C.Option("Перевести", 85, "Switch"), C.Option("Нет", 15, "", "complement")]))
    assert not ok and any("85" in f for f in failed)


def test_number_not_matched_inside_bigger_number():
    assert not textutil.number_in(81, "about 181 people and 810 votes")
    assert textutil.number_in(81, "81 percent")
    assert textutil.number_in(81, "share 0.81 of")
    assert textutil.number_in(62.5, "62.5%")
    assert not textutil.number_in(62.5, "62%")


def test_single_sum_le_100():
    frag = "Coffee 62% Tea 50%"
    ok, failed = names_failed(make(options=[C.Option("Кофе", 62), C.Option("Чай", 50)], fragment=frag))
    assert not ok and "сумма процентов ≤ 100" in failed
    ok, failed = names_failed(make(options=[C.Option("Кофе", 62), C.Option("Чай", 50)], fragment=frag, metric="multi"))
    assert ok, failed


def test_scope_required_and_no_world_wording():
    ok, failed = names_failed(make(scope=""))
    assert "охват заполнен" in failed
    ok, failed = names_failed(make(scope="в мире"))
    assert "формулировка охвата без «в мире»" in failed
    ok, failed = names_failed(make(countries=0))
    assert "охват заполнен" in failed


def test_complement_only_for_two_option_single():
    three = [C.Option("a", 81, "Switch"), C.Option("b", 10, "", "complement"), C.Option("c", 9, "", "complement")]
    ok, failed = names_failed(make(options=three))
    assert not ok
    wrong = [C.Option("a", 81, "Switch"), C.Option("b", 25, "", "complement")]
    assert not names_failed(make(options=wrong))[0]
    assert not names_failed(make(metric="share"))[0]


def test_levels():
    assert C.level_for(make(countries=1), PRIMARY) == "B"
    assert C.level_for(make(fetched_url="https://blog.example.com/x"), PRIMARY) == "C"
    assert not names_failed(make(fetched_url="https://blog.example.com/x"))[0]


def test_page_must_be_opened():
    ok, failed = names_failed(make(fetched_url="", fragment=""))
    assert "страница открыта приложением" in failed


def test_blocked_topics():
    from majority.config import DEFAULTS
    b = DEFAULTS["blockedTopics"]
    assert C.blocked_topic("Кого выберешь на выборах?", b)
    assert C.blocked_topic("Какой бог лучше", b)
    assert C.blocked_topic("Начнётся война?", b)
    assert not C.blocked_topic("Вагонетка летит на пятерых. Переведёшь стрелку?", b)
    assert not C.blocked_topic("Что выберешь: чай или кофе?", b)
    assert not C.blocked_topic("Software or hardware?", b)
