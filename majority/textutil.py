"""Текст страниц: HTML → текст, поиск чисел и вырезка фрагментов вокруг них."""
import html
import re
from html.parser import HTMLParser

SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer", "form", "button"}
BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "table", "td", "th", "caption", "figcaption"}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
        elif tag in BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP and self.skip:
            self.skip -= 1
        elif tag in BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_to_text(s):
    if "<" not in s[:2000] and ">" not in s[:2000]:
        return normalize(s)
    p = _Text()
    try:
        p.feed(s)
    except Exception:  # noqa: BLE001
        return normalize(re.sub(r"<[^>]+>", " ", s))
    return normalize("".join(p.out))


def normalize(s):
    s = html.unescape(s).replace(" ", " ").replace(" ", " ").replace(" ", " ")
    s = s.replace("−", "-").replace("–", "-")
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def _num_variants(p):
    """Как процент p может быть записан в тексте: 81, 81%, 81.0, 0.81, 81 percent, 81,0 %."""
    p = float(p)
    out = []
    if abs(p - round(p)) < 1e-9:
        i = int(round(p))
        out.append(rf"(?<![\d.,]){i}(?:[.,]0+)?(?:\s?%|\s?per\s?cent|\s?percent|\s?процент\w*)")
        out.append(rf"(?<![\d.,]){i}(?:[.,]0+)?(?![\d])")
        out.append(rf"(?<![\d.,])0[.,]{i:02d}(?![\d])")
    else:
        s = f"{p:.1f}".rstrip("0").rstrip(".")
        a, b = s.split(".") if "." in s else (s, "")
        out.append(rf"(?<![\d.,]){a}[.,]{b}\d*(?:\s?%)?")
    return out


def find_number(p, text):
    """Позиция первого вхождения процента p в тексте (сначала с «%», потом просто числом), иначе -1."""
    for pat in _num_variants(p):
        m = re.search(pat, text, re.I)
        if m:
            return m.start()
    return -1


def number_in(p, fragment):
    return find_number(p, fragment) >= 0


def fragment_around(text, pos, width=260):
    s, e = max(0, pos - width), min(len(text), pos + width)
    # аккуратно по границам слов
    while s > 0 and text[s - 1] not in " \n":
        s -= 1
    while e < len(text) and text[e] not in " \n":
        e += 1
    return text[s:e].strip()


def find_quote(quote, text):
    """Ищет дословную цитату в тексте страницы с нормализацией пробелов и кавычек. Возвращает позицию или -1."""
    if not quote:
        return -1

    def norm(x):
        x = x.lower().replace("’", "'").replace("“", '"').replace("”", '"').replace("«", '"').replace("»", '"')
        return re.sub(r"\s+", " ", x)

    t, q = norm(text), norm(quote).strip(" .…")
    i = t.find(q)
    if i >= 0:
        return i
    # цитата могла быть слегка сокращена моделью: ищем по первой половине
    half = q[: max(40, len(q) // 2)]
    return t.find(half) if len(half) >= 40 else -1


def domain(url):
    m = re.match(r"https?://([^/]+)", url or "")
    return (m.group(1).lower().removeprefix("www.") if m else "")
