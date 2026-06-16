"""Pydantic-Schemas für alle Pipeline-Phasen.

Verbindlich mit docs/02_pipeline_spec.md Sektion 7 synchron halten.
Bei Schema-Änderung: schema_version in pipeline.config.yaml inkrementieren,
Doku-Sektion 7 aktualisieren.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from pipeline import taxonomy

# === Phase 1: Inventar =========================================================


class DocumentRecord(BaseModel):
    """Inventar-Eintrag pro Markdown-Datei aus corpus_input."""

    doc_id: str  # D_<slug>
    path: str
    filename: str
    size_bytes: int
    modified_at: datetime
    sha256: str
    line_count: int
    word_count: int
    char_count: int


# === Phase 2: Normalisierung ===================================================


class CleanedDocument(BaseModel):
    """Normalisiertes Dokument mit extrahiertem Frontmatter."""

    doc_id: str
    body: str
    frontmatter: dict[str, Any]
    normalized_sha256: str


# === Phase 3: Strukturextraktion ===============================================


class DocTypeGuess(BaseModel):
    """Heuristische Dokumenttyp-Vermutung mit Confidence und Signalen."""

    label: Literal[
        "cheat_sheet",
        "tutorial",
        "wiki",
        "manual",
        "how-to",
        "explanation",
        "reference",
        "gedanke",
        "projektidee",
        "projektplanung",
        "book",
        "unklar",
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    signals: list[str]


class StructuredDocumentRecord(BaseModel):
    """Strukturell extrahiertes Dokument mit Heading-Hierarchie und Code-Blöcken."""

    doc_id: str
    title: str
    headings: list[dict[str, Any]]  # [{"level": 2, "text": "..."}]
    code_blocks: list[dict[str, Any]]  # [{"lang": "bash", "content": "..."}]
    tables_count: int
    links: list[str]
    images: list[str]
    # Obsidian-Embed-Targets aus ![[…]] (Asset-Routing, WP3). Default [] für
    # Backward-Compat mit älteren documents_structured.jsonl ohne das Feld.
    embeds: list[str] = Field(default_factory=list)
    doc_type_guess: DocTypeGuess


# === Phase 4: Segmentierung ====================================================


class SegmentRecord(BaseModel):
    """Einzelnes Segment aus einem Dokument."""

    segment_id: str  # <doc_id>-S<index:04d>
    doc_id: str
    source_path: str
    heading_path: list[str]
    segment_index: int
    text: str
    word_count: int
    char_count: int
    contains_code: bool
    contains_table: bool


# === Phase 5: Redundanz-Erkennung =============================================


class ExactDuplicateGroup(BaseModel):
    """Gruppe exakt identischer Dokumente (SHA-256 auf normalisiertem Text)."""

    sha256: str
    doc_ids: list[str]


class NearDuplicateEdge(BaseModel):
    """Kante im Ähnlichkeitsgraph: zwei Segmente mit Cosine-Similarity >= Threshold."""

    segment_id_a: str
    segment_id_b: str
    similarity: float


# === Phase 6: Embeddings + Cluster ============================================


class EmbeddingRecord(BaseModel):
    """Embedding-Vektor für ein Segment."""

    segment_id: str
    embedding: list[float]  # 768-dim für mpnet-base
    model: str


class ClusterProposal(BaseModel):
    """Initialer Cluster-Vorschlag aus Embedding-Ähnlichkeit."""

    cluster_id: str  # C_<slug>
    label_guess: str
    segment_ids: list[str]
    internal_similarity_mean: float


# === Phase 8: Qwen-Output (Frontmatter-Draft) =================================


class FrontmatterDraft(BaseModel):
    """Von Qwen generierter Frontmatter-Entwurf, validiert gegen Vault-Standard.

    ``type``/``status``/``review_status``/``confidence`` sind als ``str`` typisiert
    und werden zur Laufzeit per ``field_validator`` gegen die Taxonomie-Facade
    (``pipeline.taxonomy``) geprüft (Runtime-Membership-Check statt ``Literal``).
    Dadurch ist das Vokabular per ``config/``-YAML erweiterbar, ohne dieses Schema
    zu ändern — Single Source bleibt ``pipeline.taxonomy``.

    ``category`` bleibt bewusst ein **ungeprüfter** ``str``: unbekannte Kategorien
    sollen die Validierung NICHT hart abweisen, sondern werden von Phase 9 nach
    ``17_unsortiert`` geroutet (Catch-all, DoD) und von ``check_frontmatter`` /
    ``pkm_triage`` soft gegen ``taxonomy.ALLOWED_CATEGORIES`` gemeldet.
    """

    title: str
    slug: str
    aliases: list[str] = []
    summary: str
    type: str
    doc_role: list[str]
    category: str
    subcategory: str | None = None
    tags: list[str]
    related: list[str] = []
    used_in: list[str] = []
    parent_concept: str | None = None
    child_concepts: list[str] = []
    sources_docs: list[str]
    source_chunks: list[str]
    merged_from: list[str] = []
    status: str = "draft"
    review_status: str = "ai_drafted"
    confidence: str
    doc_version: str = "0.1.0"
    created: str  # YYYY-MM-DD
    updated: str
    last_synthesized: str
    prompt_version: str  # z.B. "v1"

    @field_validator("type", "status", "review_status", "confidence")
    @classmethod
    def _check_taxonomy_enum(cls, value: str, info: ValidationInfo) -> str:
        """Runtime-Membership-Check gegen die Taxonomie-Facade (Live-Stand)."""
        allowed = taxonomy.allowed_values(info.field_name or "")
        if value not in allowed:
            raise ValueError(
                f"{info.field_name}={value!r} nicht im Vokabular "
                f"({len(allowed)} erlaubte Werte, Quelle: pipeline.taxonomy)"
            )
        return value
