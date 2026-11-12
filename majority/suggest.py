"""Подбор новых вопросов: идём от данных — модель ищет опубликованные опросы с процентами и формулирует по ним вопрос.
Это только идеи; цифры всё равно проверяет research по реальной странице."""
from . import card as C
from .budget import BudgetExceeded
from .research import parse_json

PROMPT = """Using Google Search, find {n} published surveys or studies (YouGov, Pew Research, Ipsos, Gallup, peer-reviewed journals)
that asked people a simple "which would you choose" question with 2–4 answer options and published percentages per option.
Prefer multi-country studies. Topic focus: {topic}.
Not allowed: politics, religion, medicine, tragedies, adult themes, real people, brands.
Avoid these questions (already used): {used}
For each, write the question in Russian as it would sound in a short video (≤ 70 chars), keep the survey's own options.
Return ONLY JSON in a ```json block:
{{"items": [{{"question_ru": "", "options_ru": [""], "source_hint": "who, year, scope", "url": ""}}]}}"""


def suggest(cfg, db, llm, n=5, topic="any everyday dilemma", log=print):
    used = "; ".join(r["text"] for r in db.questions())[:2000] or "none"
    prompt = PROMPT.format(n=n, topic=topic, used=used)
    forecast = llm.estimate(prompt, search=True)
    cap = float(cfg.get("research", {}).get("budgetUsd", 0.12))
    if forecast > cap:  # подбор не относится к конкретному ролику — лимит на один вызов
        raise BudgetExceeded(f"Стоп: подбор вопросов обойдётся примерно в ${forecast:.3f}, лимит ${cap:.2f}. Ничего не вызвано.")
    res = llm.generate(prompt, search=True)
    usd = llm.cost(res.usage) if hasattr(llm, "cost") else 0.0
    db.add_cost(None, "suggest", llm.name, usd, f"подбор вопросов, прогноз ${forecast:.4f}")
    try:
        items = parse_json(res.text).get("items") or []
    except Exception as e:  # noqa: BLE001
        log(f"ответ не разобран: {e}")
        items = []
    out = []
    for it in items:
        q = (it.get("question_ru") or "").strip()
        if not q or C.blocked_topic(q, cfg["blockedTopics"]):
            continue
        qid = db.add_question(q, it.get("options_ru") or None)
        db.add_suggestion(None, q, (it.get("source_hint") or "") + (" · " + it["url"] if it.get("url") else ""))
        out.append({"qid": qid, "question": q, "hint": it.get("source_hint", "")})
    return out, usd
