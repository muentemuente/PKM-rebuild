"""WP-N2 (2.1) — Deterministischer Keyphrase-Extraktor (NB-3/9/15).

KeyBERT über den vorhandenen Embedding-Stack (mpnet, sprachagnostisch → trägt DE).
Deckt die NB-Lücke „fehlender Konzept-/Begriffs-**Extraktor**" deterministisch ab —
**kein** Qwen-Call. Das Ergebnis füllt das additive ``keyphrases``-Feld.

Der KeyBERT-Import ist **lazy** (wie ``mdformat`` in :mod:`pipeline.format_vault`,
R-1): das Modul lädt ohne installierte Dependency, und Tests injizieren über
:func:`_load_keybert` ein Fake-Modell (kein Modell-Download, deterministisch).
"""

from __future__ import annotations

import re
from typing import Any, Protocol, cast

#: Default-Embedding-Modell (identisch zum semantic-dup-Pfad, mpnet, DE-fähig).
DEFAULT_MODEL = "sentence-transformers/all-mpnet-base-v2"
#: Mindest-Body-Wortzahl, unter der Keyphrase-Extraktion sinnlos ist → leere Liste.
_MIN_BODY_WORDS = 20
#: Längen-Filter für einzelne Phrasen (Zeichen).
_MIN_PHRASE_CHARS = 3
_MAX_PHRASE_CHARS = 40
#: Tuning-Defaults (WP-N2b) — korrespondieren mit qwen.keyphrase_* in der Config.
DEFAULT_NGRAM_MAX = 3
DEFAULT_MMR_DIVERSITY = 0.6
_CODE_FENCE_RE = re.compile(r"(?ms)^([ \t]*)(`{3,}|~{3,}).*?^\1\2[ \t]*$")

#: Kuratierte deutsche Stopwords (Korpus ist DE/EN-gemischt; ergänzt das sklearn-EN-Set).
#: Bewusst klein gehalten — nur hochfrequente Funktionswörter, keine Fachbegriffe.
GERMAN_STOP_WORDS: frozenset[str] = frozenset(
    """
    aber alle allem allen aller alles als also am an ander andere anderem anderen
    auch auf aus bei bin bis bist da damit dann das dass dasselbe dazu dein deine
    dem den der derer des dessen dich die dies diese diesem diesen dieser dieses
    doch dort du durch ein eine einem einen einer eines einig einige einigem einigen
    er es etwas euer eure für gegen gewesen hab habe haben hat hatte hatten hier hin
    hinter ich ihr ihre im in indem ins ist ja jede jedem jeden jeder jedes jene
    jener kann kein keine können könnte machen man manche mehr mein meine mit muss
    musste nach nicht nichts noch nun nur ob oder ohne sehr sein seine selbst sich
    sie sind so solche solchem soll sollte sondern sonst über um und uns unser unter
    viel vom von vor war waren warst was weg weil weiter welche welchem welchen welcher
    wenn werde werden wie wieder will wir wird wirst wo wollen wollte würde würden
    zu zum zur zwar zwischen wurde wurden via dabei beim sowie bzw etc usw
    """.split()  # noqa: SIM905 — lesbarer Stopword-Block statt 130er-List-Literal
)

#: Modul-Level-Singleton-Cache: Modell **einmal** laden (Batch-Performance, A1b).
_MODEL_CACHE: dict[str, _KeyBERTLike] = {}


class _KeyBERTLike(Protocol):
    """Minimal-Schnittstelle des KeyBERT-Modells (für Tests injizierbar)."""

    def extract_keywords(self, text: str, **kwargs: Any) -> list[tuple[str, float]]: ...


def _load_keybert(model_name: str) -> _KeyBERTLike:
    """Lädt ein KeyBERT-Modell **einmal** (Modul-Singleton, WP-N2b). Tests injizieren stattdessen.

    Das Modell pro Note neu zu laden (A1a-Stand) kostete bei 165 Notes 165x Init —
    der Cache lädt es einmal und teilt es (Batch-Performance, auch für A1b).

    Raises:
        RuntimeError: wenn ``keybert`` nicht installiert ist (bewusst klar statt
            nackter ``ModuleNotFoundError``).
    """
    cached = _MODEL_CACHE.get(model_name)
    if cached is not None:
        return cached
    try:
        from keybert import KeyBERT
    except ImportError as exc:  # pragma: no cover - Dependency-Pfad
        raise RuntimeError(
            "keybert ist nicht installiert. Keyphrase-Extraktion benötigt "
            "`pip install keybert` (nutzt das vorhandene sentence-transformers-Modell)."
        ) from exc
    model = cast("_KeyBERTLike", KeyBERT(model=model_name))
    _MODEL_CACHE[model_name] = model
    return model


def _strip_code(text: str) -> str:
    """Entfernt Code-Fences (Keyphrases aus Code sind Rauschen)."""
    return _CODE_FENCE_RE.sub("", text)


def _stop_word_set() -> frozenset[str]:
    """Kombiniertes DE+EN-Stopword-Set (Korpus ist gemischt)."""
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

    return frozenset(ENGLISH_STOP_WORDS) | GERMAN_STOP_WORDS


def _is_noise_phrase(phrase: str, stop_set: frozenset[str]) -> bool:
    """``True`` wenn die Phrase **nur** aus Stopwords/Ziffern/≤2-Zeichen-Token besteht."""
    tokens = phrase.lower().split()
    if not tokens:
        return True
    return all(tok in stop_set or tok.isdigit() or len(tok) <= 2 for tok in tokens)


def _build_vectorizer(ngram_max: int, stop_set: frozenset[str]) -> Any:
    """CountVectorizer mit DE+EN-Stopwords + n-Gram-Range (1..ngram_max)."""
    from sklearn.feature_extraction.text import CountVectorizer

    return CountVectorizer(ngram_range=(1, ngram_max), stop_words=sorted(stop_set))


def extract_keyphrases(
    text: str,
    *,
    top_n: int = 8,
    ngram_max: int = DEFAULT_NGRAM_MAX,
    mmr_diversity: float = DEFAULT_MMR_DIVERSITY,
    model_name: str = DEFAULT_MODEL,
    model: _KeyBERTLike | None = None,
) -> list[str]:
    """Extrahiert bis zu ``top_n`` Keyphrases aus ``text`` (deterministisch, getunt N2b).

    Args:
        text: Artikel-Body (Markdown; Code-Fences werden ausgeschlossen).
        top_n: Maximale Anzahl Phrasen.
        ngram_max: Obere n-Gram-Grenze (Range ``(1, ngram_max)``).
        mmr_diversity: MMR-Diversität (höher → weniger redundante Phrasen).
        model_name: Embedding-Modell (Default = mpnet, DE-fähig).
        model: Injiziertes KeyBERT-Modell (Tests); ``None`` → :func:`_load_keybert`.

    Returns:
        Dedupizierte, stopword-/längen-/rausch-gefilterte Phrasen (Relevanz-Reihenfolge).
        Leerer/sehr kurzer Body → ``[]`` (kein Crash).
    """
    body = _strip_code(text)
    if len(body.split()) < _MIN_BODY_WORDS:
        return []
    stop_set = _stop_word_set()
    kb = model if model is not None else _load_keybert(model_name)
    raw = kb.extract_keywords(
        body,
        vectorizer=_build_vectorizer(ngram_max, stop_set),  # DE+EN-Stopwords + n-Gram
        use_mmr=True,
        diversity=mmr_diversity,
        top_n=top_n * 2,  # Überschuss für nachgelagerten Dedupe/Filter
    )
    out: list[str] = []
    seen: set[str] = set()
    for phrase, _score in raw:
        norm = phrase.strip().lower()
        if not (_MIN_PHRASE_CHARS <= len(norm) <= _MAX_PHRASE_CHARS):
            continue
        if norm in seen or _is_noise_phrase(norm, stop_set):
            continue
        seen.add(norm)
        out.append(phrase.strip())
        if len(out) >= top_n:
            break
    return out
