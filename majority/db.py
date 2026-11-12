"""SQLite: вопросы, карточки фактов, статусы, расходы, опубликованное."""
import json
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
  id INTEGER PRIMARY KEY,
  text TEXT NOT NULL,
  options TEXT,               -- JSON-список вариантов, если задан человеком
  status TEXT NOT NULL DEFAULT 'new',  -- new | researching | card_ready | no_data | blocked | approved | rendered | published | rejected
  note TEXT,
  created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cards (
  id INTEGER PRIMARY KEY,
  question_id INTEGER NOT NULL REFERENCES questions(id),
  data TEXT NOT NULL,          -- JSON карточки факта
  level TEXT NOT NULL,         -- A | B | C
  status TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
  checks TEXT,                 -- JSON результатов автопроверок
  created REAL NOT NULL,
  approved REAL
);
CREATE TABLE IF NOT EXISTS costs (
  id INTEGER PRIMARY KEY,
  question_id INTEGER,
  step TEXT NOT NULL,          -- suggest | research | script | assets | render | publish
  provider TEXT NOT NULL,
  usd REAL NOT NULL,
  note TEXT,
  ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS published (
  id INTEGER PRIMARY KEY,
  question_id INTEGER NOT NULL,
  question_key TEXT NOT NULL,  -- нормализованный текст вопроса (для проверки дублей)
  source_key TEXT NOT NULL,    -- первоисточник (для проверки дублей)
  target TEXT NOT NULL,        -- dry-run | tiktok-draft | ...
  ref TEXT,
  ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS suggestions (
  id INTEGER PRIMARY KEY,
  question_id INTEGER,         -- для какого вопроса без данных предложено (или NULL у suggest)
  text TEXT NOT NULL,
  source_hint TEXT,
  ts REAL NOT NULL
);
"""


class DB:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.c = sqlite3.connect(str(path))
        self.c.row_factory = sqlite3.Row
        self.c.executescript(SCHEMA)
        self.c.commit()

    def q(self, sql, *a):
        cur = self.c.execute(sql, a)
        self.c.commit()
        return cur

    # --- вопросы
    def add_question(self, text, options=None):
        row = self.q("SELECT id FROM questions WHERE lower(text)=lower(?)", text.strip()).fetchone()
        if row:
            return row["id"]
        return self.q("INSERT INTO questions(text, options, created) VALUES (?,?,?)", text.strip(),
                      json.dumps(options, ensure_ascii=False) if options else None, time.time()).lastrowid

    def question(self, qid):
        return self.q("SELECT * FROM questions WHERE id=?", qid).fetchone()

    def set_status(self, qid, status, note=None):
        self.q("UPDATE questions SET status=?, note=COALESCE(?, note) WHERE id=?", status, note, qid)

    # --- карточки
    def add_card(self, qid, data, level, checks, status="pending"):
        return self.q("INSERT INTO cards(question_id, data, level, status, checks, created) VALUES (?,?,?,?,?,?)", qid,
                      json.dumps(data, ensure_ascii=False), level, status, json.dumps(checks, ensure_ascii=False),
                      time.time()).lastrowid

    def card(self, cid):
        return self.q("SELECT * FROM cards WHERE id=?", cid).fetchone()

    def cards_for(self, qid):
        return self.q("SELECT * FROM cards WHERE question_id=? ORDER BY id", qid).fetchall()

    def approve_card(self, cid, ok=True):
        self.q("UPDATE cards SET status=?, approved=? WHERE id=?", "approved" if ok else "rejected", time.time(), cid)

    # --- расходы
    def add_cost(self, qid, step, provider, usd, note=""):
        self.q("INSERT INTO costs(question_id, step, provider, usd, note, ts) VALUES (?,?,?,?,?,?)", qid, step, provider,
               round(float(usd), 6), note, time.time())

    def spent(self, qid, step=None):
        if step:
            return float(self.q("SELECT COALESCE(SUM(usd),0) s FROM costs WHERE question_id IS ? AND step=?", qid, step)
                         .fetchone()["s"])
        return float(self.q("SELECT COALESCE(SUM(usd),0) s FROM costs WHERE question_id IS ?", qid).fetchone()["s"])

    def costs(self):
        return self.q("SELECT c.*, q.text FROM costs c LEFT JOIN questions q ON q.id=c.question_id ORDER BY c.id").fetchall()

    def questions(self, status=None):
        if status:
            return self.q("SELECT * FROM questions WHERE status=? ORDER BY id", status).fetchall()
        return self.q("SELECT * FROM questions ORDER BY id").fetchall()

    def set_card_level(self, cid, level, checks):
        self.q("UPDATE cards SET level=?, checks=? WHERE id=?", level, json.dumps(checks, ensure_ascii=False), cid)

    def suggestions_for(self, qid):
        return self.q("SELECT * FROM suggestions WHERE question_id IS ? ORDER BY id", qid).fetchall()

    # --- публикации
    def was_published(self, question_key, source_key):
        return self.q("SELECT * FROM published WHERE question_key=? OR source_key=?", question_key, source_key).fetchone()

    def add_published(self, qid, question_key, source_key, target, ref=""):
        self.q("INSERT INTO published(question_id, question_key, source_key, target, ref, ts) VALUES (?,?,?,?,?,?)", qid,
               question_key, source_key, target, ref, time.time())

    def add_suggestion(self, qid, text, hint=""):
        self.q("INSERT INTO suggestions(question_id, text, source_hint, ts) VALUES (?,?,?,?)", qid, text, hint, time.time())
