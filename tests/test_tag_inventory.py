"""Tests fuer scripts/tag_inventory.py (Block 0G.1).

Akzeptanzkriterien:
  - Normalisierung: Umlaute, lowercase, Sonderzeichen
  - Frequenz-Filter: Tags mit < 2 Files werden gefiltert
  - Frontmatter-Extraktion: yaml-tags-Feld korrekt gelesen
"""

import textwrap
from pathlib import Path

from scripts.tag_inventory import (
    _filter_min_freq,
    build_inventory,
    extract_filename_tokens,
    extract_frontmatter_tags,
    extract_heading_tokens,
    is_valid_token,
    normalize_token,
    render_inventory,
)

# === Normalisierung =============================================================


def test_normalize_token_lowercase() -> None:
    assert normalize_token("Python") == "python"
    assert normalize_token("YAML") == "yaml"


def test_normalize_token_umlauts() -> None:
    assert normalize_token("Übersicht") == "uebersicht"
    assert normalize_token("Öffnung") == "oeffnung"
    assert normalize_token("Schüler") == "schueler"
    assert normalize_token("Straße") == "strasse"


def test_normalize_token_special_chars() -> None:
    """Sonderzeichen außer Bindestrich werden entfernt."""
    assert normalize_token("rest-api") == "rest-api"
    assert normalize_token("rest_api") == "rest-api"
    assert normalize_token("REST/API!") == "restapi"


def test_normalize_token_strips_hyphens() -> None:
    assert normalize_token("-test-") == "test"
    assert normalize_token("--multi--hyphen--") == "multi-hyphen"


def test_is_valid_token_filters_short() -> None:
    assert not is_valid_token("a")
    assert is_valid_token("ai")
    assert is_valid_token("api")


def test_is_valid_token_filters_stop_words() -> None:
    assert not is_valid_token("und")
    assert not is_valid_token("the")
    assert not is_valid_token("von")
    assert is_valid_token("python")


def test_is_valid_token_filters_pure_numbers() -> None:
    assert not is_valid_token("123")
    assert is_valid_token("v2")


# === Frontmatter-Extraktion =====================================================


def test_extract_frontmatter_tags_list() -> None:
    """YAML-Liste wird korrekt ausgelesen."""
    content = textwrap.dedent(
        """\
        ---
        title: Test
        tags:
          - python
          - yaml
          - markdown
        ---
        # Body
        """
    )
    tags = extract_frontmatter_tags(content)
    assert "python" in tags
    assert "yaml" in tags
    assert "markdown" in tags


def test_extract_frontmatter_tags_inline() -> None:
    """Komma-separierte Inline-Tags werden aufgespalten."""
    content = textwrap.dedent(
        """\
        ---
        tags: python, yaml, api
        ---
        """
    )
    tags = extract_frontmatter_tags(content)
    assert "python" in tags
    assert "yaml" in tags
    assert "api" in tags


def test_extract_frontmatter_tags_missing() -> None:
    """Kein tags-Feld → leere Liste."""
    content = textwrap.dedent(
        """\
        ---
        title: Ohne Tags
        ---
        """
    )
    assert extract_frontmatter_tags(content) == []


def test_extract_frontmatter_tags_no_frontmatter() -> None:
    """Kein Frontmatter → leere Liste."""
    assert extract_frontmatter_tags("# Nur Body\n\nKein Frontmatter.") == []


def test_extract_frontmatter_tags_invalid_yaml() -> None:
    """Kaputtes YAML → leere Liste, kein Absturz."""
    content = "---\ntags: [unclosed\n---\n"
    result = extract_frontmatter_tags(content)
    assert isinstance(result, list)


# === Heading-Extraktion =========================================================


def test_extract_heading_tokens_h1_h2() -> None:
    content = "# Python Grundlagen\n## REST API Design\n### Nicht H3\n"
    tokens = extract_heading_tokens(content)
    assert "Python" in tokens
    assert "Grundlagen" in tokens
    assert "REST" in tokens
    assert "API" in tokens
    assert "Design" in tokens
    # H3 wird nicht extrahiert
    assert "Nicht" not in tokens


def test_extract_heading_tokens_backtick_removed() -> None:
    """Code-Spans in Headings werden entfernt."""
    content = "## Wie `yaml.safe_load` funktioniert\n"
    tokens = extract_heading_tokens(content)
    assert "yaml.safe_load" not in tokens


# === Dateinamen-Extraktion ======================================================


def test_extract_filename_tokens_underscores() -> None:
    tokens = extract_filename_tokens("Python_Grundlagen_Tutorial.md")
    assert "Python" in tokens
    assert "Grundlagen" in tokens
    assert "Tutorial" in tokens


def test_extract_filename_tokens_hyphens() -> None:
    tokens = extract_filename_tokens("rest-api-design.md")
    assert "rest" in tokens
    assert "api" in tokens
    assert "design" in tokens


def test_extract_filename_tokens_spaces() -> None:
    tokens = extract_filename_tokens("HTTP und HTTPS.md")
    assert "HTTP" in tokens
    assert "HTTPS" in tokens


# === Frequenz-Filter ============================================================


def test_filter_min_freq_removes_singles() -> None:
    tag_map = {
        "python": ["file1.md", "file2.md"],
        "einmal": ["file1.md"],
        "api": ["a.md", "b.md", "c.md"],
    }
    filtered = _filter_min_freq(tag_map, min_freq=2)
    assert "python" in filtered
    assert "api" in filtered
    assert "einmal" not in filtered


def test_filter_min_freq_custom_threshold() -> None:
    tag_map = {
        "python": ["a.md", "b.md"],
        "api": ["a.md", "b.md", "c.md"],
    }
    # Mit min_freq=3: python fliegt raus
    filtered = _filter_min_freq(tag_map, min_freq=3)
    assert "python" not in filtered
    assert "api" in filtered


# === Integration ================================================================


def test_build_inventory_runs_on_empty_dir(tmp_path: Path) -> None:
    """build_inventory gibt leere Dicts auf leerem Verzeichnis zurück."""
    a, b, c = build_inventory(tmp_path)
    assert a == {}
    assert b == {}
    assert c == {}


def test_build_inventory_extracts_tags(tmp_path: Path) -> None:
    """End-to-end: Tags aus zwei Files werden korrekt extrahiert."""
    for i, tag in enumerate(["python", "python"], start=1):
        content = f"---\ntags:\n  - {tag}\n---\n# Test {i}\n"
        (tmp_path / f"file{i}.md").write_text(content, encoding="utf-8")

    a, _b, _c = build_inventory(tmp_path)
    assert "python" in a
    assert len(a["python"]) == 2


def test_build_inventory_non_recursive_ignores_subfolders(tmp_path: Path) -> None:
    """Ohne recursive werden Unterordner (wie im Vault) nicht gescannt."""
    (tmp_path / "01_Grundlagen").mkdir()
    (tmp_path / "01_Grundlagen" / "a.md").write_text(
        "---\ntags:\n  - python\n---\n# A\n", encoding="utf-8"
    )
    a, _b, _c = build_inventory(tmp_path)
    assert a == {}


def test_build_inventory_recursive_scans_vault_layout(tmp_path: Path) -> None:
    """recursive findet Artikel in Unterordnern, lässt _index.md + .body.md aus."""
    folder = tmp_path / "01_Grundlagen"
    folder.mkdir()
    (folder / "a.md").write_text("---\ntags:\n  - python\n---\n# A\n", encoding="utf-8")
    (folder / "b.md").write_text("---\ntags:\n  - python\n---\n# B\n", encoding="utf-8")
    # _index.md mit Tag-Häufigkeitsliste darf NICHT mitgezählt werden
    (folder / "_index.md").write_text("# Index\n- `python`: 2\n", encoding="utf-8")
    # .body.md (Draft-Artefakt) ebenfalls nicht
    (folder / "a.body.md").write_text("---\ntags:\n  - djangoooo\n---\n# Body\n", encoding="utf-8")

    a, _b, _c = build_inventory(tmp_path, recursive=True)
    assert "python" in a
    assert len(a["python"]) == 2
    assert "djangoooo" not in a


def test_render_inventory_has_required_sections() -> None:
    """render_inventory produziert valides Markdown mit allen Sektionen."""
    a = {"python": ["a.md", "b.md"]}
    b = {"api": ["a.md", "b.md", "c.md", "d.md", "e.md", "f.md", "g.md", "h.md"]}
    c = {"readme": ["a.md", "b.md", "c.md"]}
    # min_freq_b=2 damit api (8 Belege) durchkommt; C min_freq_c=2
    output = render_inventory(a, b, c, total_files=8, min_freq_a=2, min_freq_b=2, min_freq_c=2)
    assert "## Sektion A" in output
    assert "## Sektion B" in output
    assert "## Sektion C" in output
    assert "## Cluster-Vorschlag" in output
    assert "## Stats" in output
    assert "Files gescannt: 8" in output
