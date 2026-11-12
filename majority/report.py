"""Человекочитаемая карточка для подтверждения (терминал и Markdown в output/cards)."""
import json
from pathlib import Path

from .card import LEVELS, METRICS, FactCard
from .config import ROOT



def out_dir():
    import os
    return Path(os.environ.get("MAJORITY_OUT") or ROOT / "output") / "cards"


def card_text(cid, row_card, md=False):
    fc = FactCard.from_dict(json.loads(row_card["data"]))
    checks = json.loads(row_card["checks"] or "[]")
    b = "**" if md else ""
    lines = [f"{'## ' if md else ''}Карточка #{cid} · уровень {fc.level} ({LEVELS.get(fc.level, '')}) · статус {row_card['status']}",
             "", f"{b}Вопрос:{b} {fc.question}"]
    for i, o in enumerate(fc.options, 1):
        mark = " ← большинство" if i - 1 == fc.winner else ""
        der = " (= 100 − другой вариант)" if o.derived == "complement" else ""
        lines.append(f"  {i}. {o.label} — {o.percent:g}%{der}{mark}   [в опросе: {o.source_label}]")
    lines += [
        f"{b}Кто провёл:{b} {fc.organization}, {fc.year}",
        f"{b}Выборка:{b} {fc.sample_size:,}".replace(",", " ") + f" · {b}стран:{b} {fc.countries} · {b}охват в кадре:{b} {fc.scope}",
        f"{b}Формулировка в опросе:{b} {fc.survey_wording}",
        f"{b}Тип показателя:{b} {fc.metric} — {METRICS.get(fc.metric, '?')}",
        f"{b}Поведение, а не предпочтение:{b} {'да — скажем об этом в ролике' if fc.behavior else 'нет'}",
        f"{b}Подпись источника:{b} {fc.source_short}",
        f"{b}Пояснение:{b} {fc.explanation}",
        f"{b}Источник:{b} {fc.source_url}",
        f"{b}Открытая страница:{b} {fc.fetched_url}",
        "", f"{b}Фрагмент со страницы:{b}",
    ]
    for fr in [fc.fragment] + list(fc.extra_fragments or []):
        if fr:
            lines.append(("> " if md else "  «") + fr.replace("\n", " ") + ("" if md else "»"))
    lines += ["", f"{b}Автопроверки:{b}"]
    for c in checks:
        sign = "⚠" if c.get("warn") else ("✓" if c["ok"] else "✗")
        lines.append(f"  {sign} {c['name']}: {c.get('detail', '')}")
    if fc.notes:
        lines += ["", f"{b}Заметки:{b}"] + [f"  - {n}" for n in fc.notes]
    return "\n".join(lines)


def save_card(db, cid):
    row = db.card(cid)
    OUT = out_dir()
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"q{row['question_id']:03d}-card{cid}.md"
    p.write_text(card_text(cid, row, md=True) + "\n", encoding="utf-8")
    (OUT / f"q{row['question_id']:03d}-card{cid}.json").write_text(
        json.dumps({"card_id": cid, "status": row["status"], "level": row["level"], "card": json.loads(row["data"]),
                    "checks": json.loads(row["checks"] or "[]")}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def summary_md(db, results):
    """Сводка прогона для GitHub (step summary)."""
    out = ["# Результаты исследования", ""]
    for r in results:
        q = db.question(r["qid"])
        out.append(f"### Вопрос #{r['qid']}: {q['text']}")
        out.append(f"Статус: **{r['status']}** — {r.get('note') or q['note'] or ''}  ·  потрачено ${db.spent(r['qid']):.4f}")
        if r.get("card"):
            out += ["", card_text(r["card"], db.card(r["card"]), md=True)]
        for s in db.suggestions_for(r["qid"]):
            out.append(f"- похожий вопрос с данными: {s['text']} ({s['source_hint']})")
        for cid in r.get("cards", []) or []:
            out += ["", "<details><summary>Отклонённая карточка #%d</summary>\n" % cid,
                    card_text(cid, db.card(cid), md=True), "\n</details>"]
        out.append("")
    return "\n".join(out)


def path_rel(p):
    try:
        return str(Path(p).relative_to(ROOT))
    except ValueError:
        return str(p)
