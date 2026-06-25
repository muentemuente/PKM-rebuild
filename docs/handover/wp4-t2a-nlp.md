---
title: WP4 · T2a — NLP-Dublette-Analyse (read-only)
slug: wp4-t2a-nlp
status: review
created: 2026-06-24
updated: 2026-06-24
plan: Projektplan_pipeline-v3.md
task: cc-tasks/TASK_wp4_T1c-export-und-T2a-nlp.md
gate: 4-2a
---

# WP4 · T2a — NLP-Dublette: echte Dublette oder überlappend-distinkt?

Paar: `nlp-grundlagen-und-named-entity-recognition` (A) ↔ `nlp-pkm-grundlagen` (B).
Beide DE, beide `draft`, `type: knowledge-article`. EN-Tiebreaker **N/A**.

## Vergleich

| Kriterium | A · nlp-…-ner | B · nlp-pkm-grundlagen |
|---|---|---|
| Wortzahl | **1232** | **3953** (3,2×) |
| Headings | 8 Sektionen, NER-fokussiert | 11 Kapitel, 50+ Subsektionen |
| Ordner / category | `09_KI-und-Semantische-Systeme` / ki-und-semantische-systeme | `01_Grundlagen` / grundlagen |
| Themen | NLP-Grundlagen, **NER vertieft** (dt. Modelle, Kategorien, Evaluation, Herausforderungen) | Setup/Install, Preprocessing, NER, POS, **Topic-Modeling**, **Embeddings**, **Semantic-Search**, **Auto-Tagging**, Workflows, Ressourcen |
| Framing | atomarer Serien-Baustein „**Teil 1**" (allg. NLP + NER) | monolithische End-to-End-**How-To für PKM** |
| Überlapp | „Was ist NLP", NER-Basics | dieselben + **gesamte restliche Serie** |
| tags | nlp, ner, machine-learning | nlp, text-processing, semantic-search, topic-modeling, ner, python |
| related | → `nlp-pkm-grundlagen` (B) | → `nlp-grundlagen-und-named-entity-recognition` (A), `natural-language-generation-nlg` |
| Inbound-Wikilinks | 1 (`00_Maps/moc-nlp-grundlagen.md`) | 1 (`00_Maps/moc-nlp-grundlagen.md`) |

## Entscheidender Kontext

A ist **kein Solo-Doc**, sondern Kapitel einer kuratierten `nlp-*`-Serie im KI-Ordner:
`nlp-embeddings`, `nlp-topic-modeling`, `nlp-praktische-tools-und-roadmap`,
`multimodal-nlp-systems` (+ A). B ist ein **älterer Monolith**, der inhaltlich die
**gesamte Serie** dupliziert (NER=A, Embeddings=`nlp-embeddings`,
Topic-Modeling=`nlp-topic-modeling`, Tools=`nlp-praktische-tools`), nicht nur A.
Die Embedding-Cosine 0,93 spiegelt diese breite Überlappung, nicht eine 1:1-Dublette.

## Empfehlung: **(D) Distinkt behalten** — für das Paar A↔B

Begründung: Keine saubere (K)-Richtung möglich.
- A kanonisch + B deprecaten → **massiver Unique-Verlust** (B: Setup, POS,
  Topic-Modeling, Embeddings, Semantic-Search, Auto-Tagging, Workflows).
- B kanonisch + A deprecaten → kollabiert einen kuratierten Serien-Baustein in
  einen Monolithen und beschädigt die Serienstruktur (A↔Geschwister).
- „Tiebreaker = Vollständigkeit" würde B wählen, ist hier aber irreführend:
  Vollständigkeit ≠ bessere Atomarität; B überlappt die **ganze Serie**.

A↔B sind bereits wechselseitig `related`-verlinkt + via MOC gebündelt → (D) erfüllt,
**kein Archive, kein Body-Merge, kein Content-Verlust.**

## ⚠️ Unique-Content-Flag & Eskalation

**Ja** — beide Seiten tragen substanziellen Unique-Content (s. o.). Daher niemals
(K) ohne Attic-Sicherung.

**Echte WP4-Frage (größer als 2-File-Dedupe):** Soll der **Monolith B** mittelfristig
in die Serie **dekomponiert / abgelöst** werden (restructure-Scope → **T4**, nicht T2)?
Das ist eine Struktur-/Owner-Entscheidung, kein einfacher Dubletten-Resolve.
Für T2 lautet die Empfehlung: (D) belassen, B-Dekomposition als T4-Kandidat vormerken.
