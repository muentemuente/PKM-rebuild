"""Pydantic-Schemas für alle Pipeline-Phasen.

Verbindlich mit docs/02_pipeline_spec.md Sektion 7 synchron halten.
Bei Schema-Änderung: schema_version in pipeline.config.yaml inkrementieren,
Doku-Sektion 7 aktualisieren.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

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
    frontmatter: dict
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
    headings: list[dict]  # [{"level": 2, "text": "..."}]
    code_blocks: list[dict]  # [{"lang": "bash", "content": "..."}]
    tables_count: int
    links: list[str]
    images: list[str]
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
    """Von Qwen generierter Frontmatter-Entwurf, validiert gegen Vault-Standard."""

    title: str
    slug: str
    aliases: list[str] = []
    summary: str
    type: Literal["process-document", "knowledge-article", "compact-reference"]
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
    status: Literal["draft", "review", "stable", "deprecated"] = "draft"
    review_status: Literal["ai_drafted", "human_reviewed", "verified"] = "ai_drafted"
    confidence: Literal["low", "medium", "high"]
    doc_version: str = "0.1.0"
    created: str  # YYYY-MM-DD
    updated: str
    last_synthesized: str
    prompt_version: str  # z.B. "v1"
