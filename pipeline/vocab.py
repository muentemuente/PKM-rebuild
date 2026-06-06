"""Laden des kontrollierten Tag-Vokabulars aus der YAML-Single-Source.

``config/tag_vocabulary.yaml`` (``_paths.TAG_VOCABULARY_FILE``) ist die kanonische
Quelle. Format::

    sections:
      "Sprachen & Code": [css, javascript, ...]
      ...
    synonyms:
      alias: canonical      # Alias → kanonischer Tag
      dropped: null         # verworfen

Die Markdown-Variante (``tag-system.md`` mit ``## Kern-Vokabular`` / ``## Synonym-Map``)
bleibt als Eingabeformat in ``phase_8`` / ``manage_vocab`` erhalten (Bestands-Fixtures);
dieses Modul deckt ausschließlich den YAML-Zweig ab.
"""

from __future__ import annotations

from pathlib import Path

import yaml


def load_tag_vocabulary_yaml(path: Path) -> tuple[set[str], dict[str, str | None]]:
    """Lädt (Vokabular-Set, Synonym-Map) aus ``config/tag_vocabulary.yaml``.

    Args:
        path: Pfad zur tag_vocabulary.yaml.

    Returns:
        ``(vocab, synonyms)`` — vocab = alle kanonischen Tags über alle Sektionen;
        synonyms = Alias → kanonischer Tag (``None`` = verworfen).
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sections: dict[str, list[str]] = data.get("sections") or {}
    vocab: set[str] = {tag for tags in sections.values() for tag in (tags or [])}
    synonyms: dict[str, str | None] = data.get("synonyms") or {}
    return vocab, synonyms
