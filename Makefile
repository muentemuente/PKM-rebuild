# PKM-rebuild — go-forward-Targets (Option B)
# Vollständiger Ablauf: docs/RUNBOOK_new_files.md
# Layout/Pfade: pipeline/_paths.py (PKM_PIPELINE_ROOT, default ~/projects/aktiv/pkm-pipeline)
.PHONY: setup run review review-apply ingest publish-check tag-apply reindex validate test lint

# === Setup ===================================================================

setup:                     ## Editable-Install inkl. dev-Tools (click, pytest, ruff, mypy)
	@pip install -e ".[dev]"

# === go-forward-Flow (input/ → output/) ======================================

run:                       ## input/ → (Review-Gates) → output/ (resume-fähig)
	@python -m pipeline run

review:                    ## review/decisions.md aus den Drafts erzeugen
	@python -m pipeline review

review-apply:              ## ausgefüllte review/decisions.md anwenden
	@python -m pipeline review --apply

ingest:                    ## inkrementell: input/ → Drafts (+ ingest_report.md), ohne Build
	@python -m pipeline ingest

publish-check:             ## gebauten output/-Vault validieren (vor dem Rausziehen)
	@python3 scripts/validate_vault.py

# === Vault-Pflege (Bestand) ==================================================

tag-apply:                 ## Tag-Merge-Map auf output/ anwenden (+ Backup)
	@python3 scripts/apply_tag_map.py --apply

reindex:                   ## _index.md je Ordner neu schreiben
	@python3 scripts/rebuild_indices.py

validate:                  ## Frontmatter/Enums/Slugs im output/-Vault prüfen
	@python3 scripts/validate_vault.py

# === Qualität ================================================================

test:                      ## pytest
	@python -m pytest -q

lint:                      ## ruff check + format-check + mypy
	@ruff check . && ruff format --check . && mypy pipeline/
