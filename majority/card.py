"""Карточка факта и её автопроверки."""
from dataclasses import asdict, dataclass, field

from . import textutil

METRICS = {
    "single": "один выбор из списка",
    "multi": "несколько выборов",
    "share": "доля тех, кому нравится / кто согласен",
}
LEVELS = {"A": "исследование в 10+ странах", "B": "одна-девять стран", "C": "нет данных / противоречия / пересказ"}


@dataclass
class Option:
    label: str                 # подпись в ролике
    percent: float
    source_label: str = ""     # как вариант назван в опросе
    derived: str = ""          # "" — число со страницы; "complement" — 100 − другой вариант (только для 2 вариантов, single)


@dataclass
class FactCard:
    question: str
    options: list
    organization: str          # кто провёл
    year: int
    sample_size: int
    countries: int
    scope: str                 # «42 страны», «США» — как сказать в кадре
    survey_wording: str        # точная формулировка вопроса в опросе
    metric: str                # single | multi | share
    source_url: str            # первоисточник (как ссылаться)
    fetched_url: str           # страница, которую приложение реально открыло
    fragment: str              # дословный фрагмент страницы с цифрой (для проверки, не для показа)
    level: str = "C"
    behavior: bool = False     # данные о поведении, а не о предпочтении
    explanation: str = ""      # одна фраза-пояснение для развязки
    source_short: str = ""     # «PNAS, 42 страны, 2020» — подпись в кадре
    notes: list = field(default_factory=list)
    extra_fragments: list = field(default_factory=list)

    def to_dict(self):
        d = asdict(self)
        return d

    @staticmethod
    def from_dict(d):
        d = dict(d)
        d["options"] = [o if isinstance(o, Option) else Option(**o) for o in d.get("options", [])]
        return FactCard(**{k: v for k, v in d.items() if k in FactCard.__dataclass_fields__})

    @property
    def winner(self):
        return max(range(len(self.options)), key=lambda i: self.options[i].percent)


def level_for(card, primary_domains):
    """A — 10+ стран; B — 1–9 стран; C — нет охвата или источник не первичный."""
    dom = textutil.domain(card.fetched_url or card.source_url)
    primary = any(dom == p or dom.endswith("." + p) for p in primary_domains)
    if not primary or not card.countries:
        return "C"
    return "A" if card.countries >= 10 else "B"


def check(card, primary_domains):
    """Все автопроверки. Возвращает (ok, список {name, ok, detail})."""
    res = []

    def add(name, ok, detail=""):
        res.append({"name": name, "ok": bool(ok), "detail": detail})

    frags = [card.fragment] + list(card.extra_fragments or [])
    add("варианты", 2 <= len(card.options) <= 4, f"{len(card.options)} шт.")
    for i, o in enumerate(card.options, 1):
        if o.derived == "complement":
            ok = card.metric == "single" and len(card.options) == 2
            other = card.options[2 - i] if ok else None
            ok = ok and other is not None and not other.derived and abs(o.percent - (100 - other.percent)) < 0.51
            add(f"вариант {i}: {o.percent:g}%", ok, "= 100 − второй вариант (опрос с двумя исходами)")
        else:
            hit = next((f for f in frags if textutil.number_in(o.percent, f or "")), None)
            add(f"вариант {i}: {o.percent:g}%", hit is not None, "число найдено во фрагменте" if hit else "числа нет во фрагменте")
    if card.metric == "single":
        s = sum(o.percent for o in card.options)
        add("сумма процентов ≤ 100", s <= 100.0 + 1e-9, f"{s:g}%")
    add("тип показателя", card.metric in METRICS, card.metric)
    add("охват заполнен", bool(card.scope) and card.countries > 0, f"{card.scope} ({card.countries} стр.)")
    add("кто провёл и год", bool(card.organization) and 1900 < int(card.year or 0) < 2100, f"{card.organization}, {card.year}")
    add("страница открыта приложением", bool(card.fetched_url) and bool(card.fragment), card.fetched_url)
    bad_words = [w for w in ("в мире", "все люди", "worldwide", "everyone") if w in (card.scope + " " + card.source_short).lower()]
    add("формулировка охвата без «в мире»", not bad_words, ", ".join(bad_words))
    lv = level_for(card, primary_domains)
    add("уровень не C", lv != "C", f"уровень {lv}")
    return all(r["ok"] for r in res), res


def blocked_topic(text, blocked):
    import re
    t = text.lower().replace("ё", "е")
    return next((w for w in blocked if re.search(w if w.startswith("\\b") else r"(?<![а-яa-z])" + w, t)), None)


def norm_key(s):
    import re
    return re.sub(r"[^\w]+", " ", s.lower().replace("ё", "е")).strip()
