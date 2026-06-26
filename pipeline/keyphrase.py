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
_CODE_FENCE_RE = re.compile(r"(?ms)^([ \t]*)(`{3,}|~{3,}).*?^\1\2[ \t]*$")


class _KeyBERTLike(Protocol):
    """Minimal-Schnittstelle des KeyBERT-Modells (für Tests injizierbar)."""

    def extract_keywords(self, text: str, **kwargs: Any) -> list[tuple[str, float]]: ...


def _load_keybert(model_name: str) -> _KeyBERTLike:
    """Lädt ein KeyBERT-Modell (lazy). Tests monkeypatchen diese Factory.

    Raises:
        RuntimeError: wenn ``keybert`` nicht installiert ist (bewusst klar statt
            nackter ``ModuleNotFoundError``).
    """
    try:
        from keybert import KeyBERT
    except ImportError as exc:  # pragma: no cover - Dependency-Pfad
        raise RuntimeError(
            "keybert ist nicht installiert. Keyphrase-Extraktion benötigt "
            "`pip install keybert` (nutzt das vorhandene sentence-transformers-Modell)."
        ) from exc
    return cast("_KeyBERTLike", KeyBERT(model=model_name))


def _strip_code(text: str) -> str:
    """Entfernt Code-Fences (Keyphrases aus Code sind Rauschen)."""
    return _CODE_FENCE_RE.sub("", text)


def extract_keyphrases(
    text: str,
    *,
    top_n: int = 8,
    model_name: str = DEFAULT_MODEL,
    model: _KeyBERTLike | None = None,
) -> list[str]:
    """Extrahiert bis zu ``top_n`` Keyphrases aus ``text`` (deterministisch).

    Args:
        text: Artikel-Body (Markdown; Code-Fences werden ausgeschlossen).
        top_n: Maximale Anzahl Phrasen.
        model_name: Embedding-Modell (Default = mpnet, DE-fähig).
        model: Injiziertes KeyBERT-Modell (Tests); ``None`` → :func:`_load_keybert`.

    Returns:
        Dedupizierte, längen-/stopword-gefilterte Phrasen (Original-Reihenfolge nach
        Relevanz). Leerer/sehr kurzer Body → ``[]`` (kein Crash).
    """
    body = _strip_code(text)
    if len(body.split()) < _MIN_BODY_WORDS:
        return []
    kb = model if model is not None else _load_keybert(model_name)
    raw = kb.extract_keywords(
        body,
        keyphrase_ngram_range=(1, 2),
        stop_words=None,  # mehrsprachig → kein EN-Stopword-Set erzwingen
        use_mmr=True,
        diversity=0.5,
        top_n=top_n * 2,  # Überschuss für nachgelagerten Dedupe/Filter
    )
    out: list[str] = []
    seen: set[str] = set()
    for phrase, _score in raw:
        norm = phrase.strip().lower()
        if not (_MIN_PHRASE_CHARS <= len(norm) <= _MAX_PHRASE_CHARS):
            continue
        if norm in seen:
            continue
        seen.add(norm)
        out.append(phrase.strip())
        if len(out) >= top_n:
            break
    return out
