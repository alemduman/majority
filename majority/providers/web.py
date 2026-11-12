"""Открывает страницы источников. Сам ходит по ссылке; если издатель не отдаёт страницу роботу (403, капча),
пробует открытые зеркала той же статьи: PubMed Central и Europe PMC (по DOI). Число всё равно берётся
только из реально полученного текста."""
import gzip
import io
import json
import re
import urllib.parse
import urllib.request

from .. import textutil

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36")
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s?#\"'<>]+")


class FetchError(Exception):
    pass


def _get(url, timeout=30, accept="text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Language": "en,ru;q=0.8",
                                               "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(15_000_000)
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return r.geturl(), r.headers.get("Content-Type", ""), raw


def _to_text(ctype, raw):
    if "pdf" in ctype or raw[:5] == b"%PDF-":
        try:
            from pypdf import PdfReader
        except ImportError as e:  # noqa: F841
            raise FetchError("PDF: нет пакета pypdf")
        pdf = PdfReader(io.BytesIO(raw))
        return textutil.normalize("\n".join((p.extract_text() or "") for p in pdf.pages[:60]))
    enc = "utf-8"
    m = re.search(r"charset=([\w-]+)", ctype)
    if m:
        enc = m.group(1)
    s = raw.decode(enc, errors="replace")
    if "xml" in ctype and "<article" in s[:5000]:
        s = re.sub(r"<(/?)(sec|p|title|table-wrap|caption|td|th|tr)\b", r"<\1div", s)
    return textutil.html_to_text(s)


def _blocked(text):
    t = text[:3000].lower()
    return len(text) < 600 or any(w in t for w in ("just a moment", "verify you are human", "captcha", "access denied",
                                                   "enable javascript and cookies", "are you a robot"))


class WebFetcher:
    name = "web"

    def __init__(self, log=print):
        self.log = log

    def fetch(self, url):
        """→ (итоговый URL, текст страницы). Бросает FetchError, если ничего не открылось."""
        tried = []
        for u in self._candidates(url):
            try:
                final, ctype, raw = _get(u)
                text = _to_text(ctype, raw)
                if _blocked(text):
                    tried.append(f"{u}: страница-заглушка ({len(text)} симв.)")
                    continue
                return final, text
            except Exception as e:  # noqa: BLE001
                tried.append(f"{u}: {type(e).__name__} {str(e)[:120]}")
        raise FetchError("не открылось: " + " | ".join(tried))

    def _candidates(self, url):
        yield url
        doi = self._doi(url)
        if not doi:
            return
        # Europe PMC: ищем PMCID по DOI, затем открытый полный текст
        try:
            q = urllib.parse.quote(f'DOI:"{doi}"')
            _, _, raw = _get(f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={q}&format=json&resultType=lite",
                             accept="application/json")
            hits = json.loads(raw).get("resultList", {}).get("result", [])
            pmcid = next((h.get("pmcid") for h in hits if h.get("pmcid")), None)
        except Exception as e:  # noqa: BLE001
            self.log(f"  Europe PMC поиск: {e}")
            pmcid = None
        if pmcid:
            yield f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
            yield f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
        yield f"https://doi.org/{doi}"

    @staticmethod
    def _doi(url):
        m = DOI_RE.search(urllib.parse.unquote(url or ""))
        return m.group(0).rstrip(".,);]") if m else None


def resolve_redirect(url, timeout=20):
    """Ссылки поиска Gemini ведут через vertexaisearch.cloud.google.com — узнаём настоящий адрес."""
    if "grounding-api-redirect" not in url:
        return url
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.geturl()
    except urllib.error.HTTPError as e:
        return e.headers.get("Location") or e.url or url
    except Exception:  # noqa: BLE001
        return url
