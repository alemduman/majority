"""Исследование вопроса: поиск первоисточника → открыть страницу → найти каждое число в тексте страницы →
карточка факта → автопроверки → уровень. Цифры из памяти модели не принимаются: всё, чего нет в
полученном тексте, отбрасывается. Нет подтверждённых данных — статус no_data и 3 похожих вопроса."""
import hashlib
import json
import re
from pathlib import Path

from . import card as C
from . import textutil
from .budget import Budget, BudgetExceeded
from .config import ROOT

SEARCH_PROMPT = """You are a fact researcher for short vertical videos "What would you choose — and what does the majority choose".
Question (Russian): «{question}»
{options_hint}
Find PRIMARY sources — the survey or study itself (YouGov, Pew Research, Ipsos, Gallup, peer-reviewed journals) —
that asked people this question (or a very close one) and published the percentage for each answer option.

Rules:
- Go from data to question: the options must be exactly the answer options of that survey. Never add an option the survey did not have.
- Prefer multi-country studies, then the biggest/most recent. Prefer the page where the percentages are printed (article full text, results page, PDF topline), not a press release.
- source_url must be the primary page (publisher/pollster). No news retellings, blogs, Wikipedia, aggregators.
- Each percentage needs "quote": an exact sentence or table row copied from that page which contains the number. If you cannot quote it, do not give the number.
- If the source reports only one share of a two-way choice (e.g. 81% chose A, the rest chose B), give B with "derived": "complement" and no quote.
- metric: "single" (one answer from a list; shares sum to ≤100), "multi" (several answers allowed), "share" (separate % who agree/like, not a choice between options).
- behavior=true if the data describe what people do/own/buy rather than what they prefer.
- Topics that are NOT allowed: politics, religion, medicine, tragedies, adult themes, real people. If the question is such, return found=false.
- If no primary data with percentages exists, return found=false and give 3 similar questions (in Russian) that DO have primary data, with a source hint.
- Russian fields: label_ru — 1–3 word caption for the option; scope_ru — coverage as it may be said on screen (e.g. «42 страны», «США», «24 страны»), never «в мире»/«все люди»; source_short_ru — e.g. «PNAS, 42 страны, 2020»; explanation_ru — one short line (≤ 90 chars) that explains the result without new numbers.

Return ONLY a JSON object inside a ```json block:
{{"found": true,
 "candidates": [{{"organization": "", "publication": "", "year": 0, "sample_size": 0, "countries": 0,
   "scope_ru": "", "survey_wording": "exact question text used in the survey", "metric": "single",
   "source_url": "", "doi": "", "behavior": false, "source_short_ru": "", "explanation_ru": "",
   "options": [{{"source_label": "answer option as in the survey", "label_ru": "", "percent": 0, "quote": "", "derived": ""}}],
   "notes": ""}}],
 "similar": [{{"question_ru": "", "source_hint": ""}}]}}
Give at most {max_candidates} candidates, best first."""

EXTRACT_PROMPT = """Below is text of a web page ({url}). Survey question: «{wording}».
For each answer option, copy the EXACT sentence or table row from THIS TEXT that contains its percentage.
Do not use any knowledge outside this text. If the text does not contain the percentage, return null for it.
Options: {options}
Also copy exact sentences that state the sample size and the number of countries, if present.
Return ONLY JSON in a ```json block:
{{"options": [{{"source_label": "", "percent": 0, "quote": ""}}], "sample_quote": "", "countries_quote": "", "year_quote": ""}}

PAGE TEXT:
{text}"""

SIMILAR_PROMPT = """The question «{question}» has no primary survey data with percentages.
Using Google Search, propose 3 similar questions (in Russian, same spirit, "what would you choose") for which primary
survey/study data with per-option percentages DO exist (YouGov, Pew, Ipsos, Gallup, journals).
No politics, religion, medicine, tragedies, adult themes, real people.
Return ONLY JSON in a ```json block: {{"similar": [{{"question_ru": "", "source_hint": "who, year, scope"}}]}}"""


def parse_json(text):
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    raw = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        raw = re.sub(r",\s*([}\]])", r"\1", raw)  # висячие запятые
        return json.loads(raw)


def _int(x):
    try:
        return int(re.sub(r"[^\d]", "", str(x)) or 0)
    except Exception:  # noqa: BLE001
        return 0


def _int_on_page(n, text):
    """Есть ли целое n на странице в любой записи: 70000, 70,000, 70 000, 70.000, 70k."""
    if not n:
        return False
    s = str(int(n))
    groups = re.sub(r"(?<=\d)(?=(\d{3})+$)", "_", s).split("_")
    sep = r"[,\s. ]?"
    pat = r"(?<![\d.,])" + sep.join(groups) + r"(?![\d])"
    if re.search(pat, text):
        return True
    if int(n) >= 1000 and int(n) % 1000 == 0 and re.search(rf"(?<![\d.,]){int(n) // 1000}\s?[kK](?![a-z])", text):
        return True
    return False


def _keywords(label):
    words = re.findall(r"[A-Za-zА-Яа-яЁё]{3,}", label or "")
    stop = {"the", "and", "for", "with", "not", "что", "или", "это"}
    return [w.lower() for w in words if w.lower() not in stop][:4]


def locate(percent, quote, label, text):
    """Ищет число на странице. → (фрагмент, как найдено) или (None, причина)."""
    if quote:
        pos = textutil.find_quote(quote, text)
        if pos >= 0:
            frag = textutil.fragment_around(text, pos + min(len(quote), 400) // 2, width=max(260, len(quote) // 2 + 120))
            if textutil.number_in(percent, frag):
                return frag, "дословная цитата найдена на странице"
    # цитата не совпала: ищем само число рядом со словами варианта
    kws = _keywords(label)
    for pat in textutil._num_variants(percent)[:1] + textutil._num_variants(percent)[1:2]:
        for m in re.finditer(pat, text, re.I):
            frag = textutil.fragment_around(text, m.start(), width=220)
            low = frag.lower()
            if kws and any(k in low for k in kws):
                return frag, f"цитата не совпала дословно; число найдено рядом со словом «{next(k for k in kws if k in low)}»"
    return None, "числа нет на странице"


def _relevant_chunks(text, wording, labels, limit):
    """Для шага извлечения: абзацы с процентами и словами вопроса/вариантов, чтобы не слать модели всю страницу."""
    kws = set(_keywords(wording)) | {k for lb in labels for k in _keywords(lb)}
    paras = [p for p in text.split("\n") if p.strip()]
    scored = []
    for i, p in enumerate(paras):
        low = p.lower()
        score = (2 if re.search(r"\d\s?%|percent", low) else 0) + sum(1 for k in kws if k in low)
        if score >= 2:
            scored.append((i, p))
    out, n = [], 0
    for _, p in scored:
        if n + len(p) > limit:
            break
        out.append(p)
        n += len(p)
    return "\n".join(out) or text[:limit]


class Researcher:
    def __init__(self, cfg, db, llm, fetcher, log=print):
        self.cfg, self.db, self.llm, self.fetcher, self.log = cfg, db, llm, fetcher, log
        self.rcfg = cfg.get("research", {})
        self.pages_dir = Path(cfg.get("pagesDir") or ROOT / "data" / "pages")

    # ---------- платный вызов с прогнозом и журналом
    def _call(self, budget, what, prompt, search):
        forecast = self.llm.estimate(prompt, search=search)
        budget.guard("research", forecast, what, cap=self.rcfg.get("budgetUsd"))
        res = self.llm.generate(prompt, search=search)
        usd = self.llm.cost(res.usage) if hasattr(self.llm, "cost") else 0.0
        budget.record("research", self.llm.name, usd, f"{what}: in={res.usage.get('in', 0):.0f} out={res.usage.get('out', 0):.0f}"
                      f" search={res.usage.get('search', 0)} прогноз ${forecast:.4f}")
        self.log(f"  {what}: ${usd:.4f} (прогноз ${forecast:.4f})")
        return res

    # ---------- основной сценарий
    def research(self, question, options=None):
        qid = self.db.add_question(question, options)
        blocked = C.blocked_topic(question, self.cfg["blockedTopics"])
        if blocked:
            self.db.set_status(qid, "blocked", f"запрещённая тема ({blocked})")
            return {"qid": qid, "status": "blocked", "note": f"тема под запретом: «{blocked}»"}
        self.db.set_status(qid, "researching")
        budget = Budget(self.db, qid, self.cfg["budget"]["ceilingUsd"])
        try:
            return self._research(qid, question, options, budget)
        except BudgetExceeded as e:
            self.db.set_status(qid, "stopped", str(e))
            return {"qid": qid, "status": "stopped", "note": str(e)}

    def _research(self, qid, question, options, budget):
        hint = ("Options proposed by the editor (use only if the survey had exactly these): " + "; ".join(options)) if options else ""
        prompt = SEARCH_PROMPT.format(question=question, options_hint=hint, max_candidates=self.rcfg.get("maxCandidates", 4))
        res = self._call(budget, "поиск источников", prompt, search=True)
        try:
            data = parse_json(res.text)
        except Exception as e:  # noqa: BLE001
            self.log(f"  ответ модели не разобран: {e}; текст: {res.text[:300]}")
            data = {"found": False, "candidates": [], "similar": []}
        cands = (data.get("candidates") or [])[: self.rcfg.get("maxCandidates", 4)] if data.get("found") else []
        grounding = [s["url"] for s in res.sources]

        cards = []
        for i, c in enumerate(cands, 1):
            self.log(f"  кандидат {i}: {c.get('organization')} {c.get('year')} — {c.get('source_url')}")
            fc, checks, ok = self._verify(c, grounding, budget)
            if fc is None:
                self.log(f"    ✗ {checks}")
                continue
            fc.question = question
            lv = C.level_for(fc, self.cfg["primarySources"])
            fc.level = lv
            cid = self.db.add_card(qid, fc.to_dict(), lv, checks, status="pending" if ok else "failed")
            cards.append((cid, fc, ok, checks))
            self.log(f"    {'✓' if ok else '✗'} карточка #{cid}, уровень {lv}"
                     + ("" if ok else ": " + "; ".join(f"{x['name']} — {x['detail']}" for x in checks if not x['ok'])))

        good = [x for x in cards if x[2]]
        if not good:
            sims = data.get("similar") or []
            if len(sims) < 3:
                try:
                    r2 = self._call(budget, "похожие вопросы", SIMILAR_PROMPT.format(question=question), search=True)
                    sims = (parse_json(r2.text).get("similar") or []) + sims
                except BudgetExceeded:
                    raise
                except Exception as e:  # noqa: BLE001
                    self.log(f"  похожие вопросы не получены: {e}")
            sims = [s for s in sims if s.get("question_ru") and not C.blocked_topic(s["question_ru"], self.cfg["blockedTopics"])][:3]
            for s in sims:
                self.db.add_suggestion(qid, s["question_ru"], s.get("source_hint", ""))
            why = "нет подтверждённых данных" if cands else "модель не нашла первоисточник с процентами"
            self.db.set_status(qid, "no_data", why)
            return {"qid": qid, "status": "no_data", "note": why, "similar": sims,
                    "cards": [x[0] for x in cards], "spent": budget.spent}

        good.sort(key=lambda x: ({"A": 0, "B": 1}.get(x[1].level, 2), -x[1].countries, -int(x[1].year or 0)))
        best_cid, best, _, best_checks = good[0]
        winners = {C.norm_key(x[1].options[x[1].winner].source_label or x[1].options[x[1].winner].label) for x in good}
        if len(winners) > 1 and self.rcfg.get("conflictPolicy", "C") == "C":
            note = "опросы расходятся: " + "; ".join(f"#{x[0]} {x[1].source_short} → {x[1].options[x[1].winner].label}" for x in good)
            best.notes.append(note)
            best.level = "C"
            best_checks.append({"name": "опросы не расходятся", "ok": False, "detail": note})
            self.db.set_card_level(best_cid, "C", best_checks)
            self.db.set_status(qid, "conflict", note)
            return {"qid": qid, "status": "conflict", "note": note, "card": best_cid, "spent": budget.spent}
        self.db.set_status(qid, "card_ready", f"карточка #{best_cid} ждёт подтверждения")
        return {"qid": qid, "status": "card_ready", "card": best_cid, "level": best.level, "spent": budget.spent,
                "others": [x[0] for x in good[1:]]}

    # ---------- проверка одного кандидата по реальной странице
    def _verify(self, c, grounding, budget):
        url = (c.get("source_url") or "").strip()
        if c.get("doi") and not url:
            url = "https://doi.org/" + c["doi"]
        if not url:
            return None, "нет ссылки на источник", False
        urls = [url] + [g for g in grounding if textutil.domain(g) == textutil.domain(url) and g != url]
        page_url, text, err = None, None, ""
        for u in urls[:3]:
            try:
                page_url, text = self.fetcher.fetch(u)
                break
            except Exception as e:  # noqa: BLE001
                err = str(e)[:400]
        if text is None:
            return None, f"страница не открылась ({err})", False
        text = text[: self.rcfg.get("maxPageChars", 60000) * 4]
        self._save_page(page_url, text)

        opts = c.get("options") or []
        found = {}
        for j, o in enumerate(opts):
            if o.get("derived") == "complement":
                continue
            frag, how = locate(o.get("percent"), o.get("quote"), o.get("source_label"), text)
            if frag:
                found[j] = (frag, how)
        missing = [j for j, o in enumerate(opts) if o.get("derived") != "complement" and j not in found]
        if missing and opts:
            # второй шанс: модель читает только эту страницу и копирует строки с числами, код снова проверяет
            chunk = _relevant_chunks(text, c.get("survey_wording", ""), [o.get("source_label", "") for o in opts],
                                     self.rcfg.get("maxPageChars", 60000))
            try:
                r = self._call(budget, "извлечение со страницы", EXTRACT_PROMPT.format(
                    url=page_url, wording=c.get("survey_wording", ""), text=chunk,
                    options="; ".join(f"{o.get('source_label')} ({o.get('percent')}%)" for o in opts)), search=False)
                ex = parse_json(r.text)
                for j in missing:
                    lab = C.norm_key(opts[j].get("source_label", ""))
                    for eo in ex.get("options") or []:
                        if not eo or not eo.get("quote"):
                            continue
                        if C.norm_key(eo.get("source_label", "")) == lab or len(opts) == len(ex.get("options") or []):
                            if eo.get("percent") is not None and abs(float(eo["percent"]) - float(opts[j]["percent"])) > 0.051:
                                continue  # на странице другое число — значит, исходная цифра неверна
                            frag, how = locate(opts[j]["percent"], eo["quote"], opts[j].get("source_label"), text)
                            if frag:
                                found[j] = (frag, how + " (шаг извлечения)")
                                break
            except BudgetExceeded:
                raise
            except Exception as e:  # noqa: BLE001
                self.log(f"    извлечение не удалось: {e}")

        if len(opts) == 2:
            for j, o in enumerate(opts):
                if o.get("derived") == "complement" and not opts[1 - j].get("derived"):
                    o["percent"] = round(100 - float(opts[1 - j].get("percent") or 0), 1)
        frags, options = [], []
        for j, o in enumerate(opts):
            options.append(C.Option(label=o.get("label_ru") or o.get("source_label") or f"Вариант {j + 1}",
                                    percent=float(o.get("percent") or 0), source_label=o.get("source_label", ""),
                                    derived="complement" if o.get("derived") == "complement" else ""))
            if j in found and found[j][0] not in frags:
                frags.append(found[j][0])
        fc = C.FactCard(
            question="", options=options, organization=c.get("organization", ""), year=_int(c.get("year")),
            sample_size=_int(c.get("sample_size")), countries=_int(c.get("countries")), scope=c.get("scope_ru", ""),
            survey_wording=c.get("survey_wording", ""), metric=c.get("metric", ""), source_url=url, fetched_url=page_url,
            fragment=frags[0] if frags else "", extra_fragments=frags[1:], behavior=bool(c.get("behavior")),
            explanation=c.get("explanation_ru", ""), source_short=c.get("source_short_ru", ""),
            notes=[x for x in [c.get("notes", "")] if x] + [f"вариант {j + 1}: {found[j][1]}" for j in sorted(found)])
        ok, checks = C.check(fc, self.cfg["primarySources"])
        # не блокирующие сверки со страницей — видны человеку при подтверждении
        for name, val in (("размер выборки на странице", fc.sample_size), ("число стран на странице", fc.countries),
                          ("год на странице", fc.year)):
            on = _int_on_page(val, text)
            checks.append({"name": name, "ok": True, "warn": not on, "detail": f"{val}: {'есть' if on else 'НЕ найдено — проверь глазами'}"})
        return fc, checks, ok

    def _save_page(self, url, text):
        """Копия полученного текста — для аудита (в git не попадает)."""
        try:
            self.pages_dir.mkdir(parents=True, exist_ok=True)
            h = hashlib.sha1(url.encode()).hexdigest()[:16]
            (self.pages_dir / f"{h}.txt").write_text(url + "\n\n" + text, encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
