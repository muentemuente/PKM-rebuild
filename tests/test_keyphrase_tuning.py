"""Tests für WP-N2b — Keyphrase-Tuning (Stopwords/Post-Filter/Dedup/Single-Load).

Kein Modell-Download: KeyBERT wird injiziert. Verifiziert, dass Rausch-Phrasen
(reine Stopwords/Ziffern/≤2-Zeichen) gedroppt werden, Lowercase-Dedup greift und
das Modell als Modul-Singleton nur einmal geladen wird.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import keyphrase


class _FakeKeyBERT:
    def __init__(self, phrases: list[tuple[str, float]]) -> None:
        self._phrases = phrases

    def extract_keywords(self, text: str, **kwargs: object) -> list[tuple[str, float]]:
        return self._phrases


def test_noise_phrase_predicate() -> None:
    stop = keyphrase._stop_word_set()
    assert keyphrase._is_noise_phrase("der die das", stop) is True  # nur DE-Stopwords
    assert keyphrase._is_noise_phrase("the and of", stop) is True  # nur EN-Stopwords
    assert keyphrase._is_noise_phrase("12 34", stop) is True  # nur Ziffern
    assert keyphrase._is_noise_phrase("ab cd", stop) is True  # nur ≤2-Zeichen
    assert keyphrase._is_noise_phrase("rest api", stop) is False  # Content


def test_tuning_drops_noise_and_dedupes() -> None:
    fake = _FakeKeyBERT(
        [
            ("der die das", 0.95),  # nur Stopwords → drop
            ("12 34", 0.90),  # nur Ziffern → drop
            ("ab cd", 0.85),  # nur ≤2-Zeichen → drop
            ("rest api", 0.80),  # Content → keep
            ("Rest API", 0.75),  # Lowercase-Dedup → drop
            ("python pandas", 0.70),  # keep
        ]
    )
    body = "wort " * 50
    out = keyphrase.extract_keyphrases(body, model=fake)
    assert out == ["rest api", "python pandas"]


def test_german_stopwords_present() -> None:
    stop = keyphrase._stop_word_set()
    for w in ("und", "für", "der", "mit", "the", "and"):
        assert w in stop


def test_model_single_load_uses_cache(monkeypatch) -> None:
    sentinel = object()
    monkeypatch.setitem(keyphrase._MODEL_CACHE, "test-model", sentinel)
    # Cache-Treffer → kein keybert-Import, dasselbe Objekt zurück.
    assert keyphrase._load_keybert("test-model") is sentinel


def test_existing_short_body_still_empty() -> None:
    fake = _FakeKeyBERT([("ignored", 0.9)])
    assert keyphrase.extract_keyphrases("zu kurz", model=fake) == []
