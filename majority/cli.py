"""Командная строка: python -m majority <команда>.

  suggest  [-n 5] [--topic ...]          подобрать вопросы, у которых есть данные опросов
  research "вопрос" [...] [--options ...] найти первоисточник, проверить числа, собрать карточку
  show     <card_id> | --question <id>    показать карточку
  approve  <card_id> [--reject] [--yes]   подтвердить (человек) — без этого дальше ничего не идёт
  render   <question_id>                  этап 2
  publish  <question_id> --publish        этап 4 (по умолчанию dry-run)
  run      "вопрос"                       research → (approve человеком) → render → publish(dry-run)
  costs    [--question id]                журнал расходов
"""
import argparse
import json
import os
import sys

from . import config, providers, report
from .db import DB
from .research import Researcher

STAGE = 1  # какой этап уже сделан


def _db():
    return DB(config.db_path())


def cmd_research(a, cfg, db):
    r = Researcher(cfg, db, providers.llm(cfg), providers.fetcher(cfg))
    results = []
    opts = [o.strip() for o in a.options.split("|")] if a.options else None
    for q in a.questions:
        print(f"\n▶ {q}")
        res = r.research(q, opts)
        results.append(res)
        _print_result(db, res)
    if a.summary:
        with open(a.summary, "a", encoding="utf-8") as f:
            f.write(report.summary_md(db, results) + "\n")
    return 0


def _print_result(db, res):
    print(f"  статус: {res['status']}" + (f" — {res['note']}" if res.get("note") else "") +
          f" · потрачено ${db.spent(res['qid']):.4f}")
    if res.get("card"):
        p = report.save_card(db, res["card"])
        print(report.card_text(res["card"], db.card(res["card"])))
        print(f"  карточка сохранена: {report.path_rel(p)}")
    for cid in res.get("cards", []) or []:
        report.save_card(db, cid)
    for s in res.get("similar", []) or []:
        print(f"  похожий вопрос с данными: {s['question_ru']} ({s.get('source_hint', '')})")


def cmd_show(a, cfg, db):
    ids = [a.card] if a.card else [c["id"] for c in db.cards_for(a.question)]
    for cid in ids:
        print(report.card_text(cid, db.card(cid)))
        print()
    return 0


def cmd_approve(a, cfg, db):
    row = db.card(a.card)
    if not row:
        print("нет такой карточки")
        return 2
    print(report.card_text(a.card, row))
    if a.reject:
        db.approve_card(a.card, ok=False)
        db.set_status(row["question_id"], "rejected", f"карточка #{a.card} отклонена человеком")
        print("✗ отклонено")
        return 0
    checks = json.loads(row["checks"] or "[]")
    if row["level"] == "C" or row["status"] != "pending" or not all(c["ok"] for c in checks):
        print(f"Нельзя подтвердить: уровень {row['level']}, статус {row['status']}, "
              f"не пройдено: {[c['name'] for c in checks if not c['ok']]}")
        return 3
    if not a.yes:
        if not sys.stdin.isatty():
            print("Нужно подтверждение человека: добавь --yes (или запусти в терминале).")
            return 4
        if input("Подтвердить карточку? [y/N] ").strip().lower() not in ("y", "yes", "д", "да"):
            print("не подтверждено")
            return 1
    db.approve_card(a.card, ok=True)
    db.set_status(row["question_id"], "approved", f"карточка #{a.card} подтверждена")
    report.save_card(db, a.card)
    print("✓ подтверждено")
    return 0


def cmd_suggest(a, cfg, db):
    from .suggest import suggest
    items, usd = suggest(cfg, db, providers.llm(cfg), n=a.n, topic=a.topic)
    for it in items:
        print(f"  #{it['qid']} {it['question']} — {it['hint']}")
    print(f"потрачено ${usd:.4f}")
    return 0


def cmd_costs(a, cfg, db):
    rows = db.costs()
    if a.question:
        rows = [r for r in rows if r["question_id"] == a.question]
    total, by_q = 0.0, {}
    for r in rows:
        total += r["usd"]
        k = (r["question_id"], r["text"] or "(подбор вопросов)")
        by_q.setdefault(k, {}).setdefault(r["step"], 0.0)
        by_q[k][r["step"]] += r["usd"]
    for (qid, text), steps in by_q.items():
        s = sum(steps.values())
        print(f"#{qid or '-'} {text[:60]}: ${s:.4f}  (" + ", ".join(f"{k} ${v:.4f}" for k, v in steps.items()) + ")")
    print(f"Итого: ${total:.4f} · записей {len(rows)} · потолок на ролик ${cfg['budget']['ceilingUsd']:.2f}")
    return 0


def cmd_stage(name, n):
    def f(a, cfg, db):
        print(f"«{name}» — это этап {n}; сейчас сделан этап {STAGE}. Жду подтверждения, чтобы делать дальше.")
        return 5
    return f


def cmd_run(a, cfg, db):
    a.questions, a.options, a.summary = [a.question], a.options, a.summary
    cmd_research(a, cfg, db)
    q = db.questions()
    row = next((r for r in q if r["text"].lower() == a.question.strip().lower()), None)
    if row and row["status"] == "card_ready":
        print("\nДальше нужно подтверждение человека: python -m majority approve <card_id>. Рендер — этап 2.")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="majority", description="Что выберешь ты — и что выбирает большинство")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("research")
    s.add_argument("questions", nargs="+")
    s.add_argument("--options", help="варианты через |, если заданы человеком")
    s.add_argument("--summary", help="дописать Markdown-сводку в файл (для GitHub)")
    s = sub.add_parser("show")
    s.add_argument("card", nargs="?", type=int)
    s.add_argument("--question", type=int)
    s = sub.add_parser("approve")
    s.add_argument("card", type=int)
    s.add_argument("--reject", action="store_true")
    s.add_argument("--yes", action="store_true", help="подтверждаю как человек (для неинтерактивного запуска)")
    s = sub.add_parser("suggest")
    s.add_argument("-n", type=int, default=5)
    s.add_argument("--topic", default="any everyday dilemma")
    s = sub.add_parser("costs")
    s.add_argument("--question", type=int)
    s = sub.add_parser("render")
    s.add_argument("question", type=int)
    s = sub.add_parser("publish")
    s.add_argument("question", type=int)
    s.add_argument("--publish", action="store_true")
    s = sub.add_parser("run")
    s.add_argument("question")
    s.add_argument("--options")
    s.add_argument("--summary")
    a = p.parse_args(argv)
    cfg = config.load()
    print(f"[режим: {'MOCK (без ключей)' if cfg['mock'] else 'боевой'} · база {os.path.relpath(config.db_path())}]")
    db = _db()
    fn = {"research": cmd_research, "show": cmd_show, "approve": cmd_approve, "suggest": cmd_suggest, "costs": cmd_costs,
          "render": cmd_stage("render", 2), "publish": cmd_stage("publish", 4), "run": cmd_run}[a.cmd]
    return fn(a, cfg, db) or 0


if __name__ == "__main__":
    sys.exit(main())
