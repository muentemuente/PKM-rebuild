# PKM-rebuild — Abschluss-Targets (2026-06-06)
# Siehe docs/RUNBOOK_new_files.md fuer den vollstaendigen Ablauf.
.PHONY: tag-apply reindex validate add-files

tag-apply:
	@python3 scripts/apply_tag_map.py --apply

reindex:
	@python3 scripts/rebuild_indices.py

validate:
	@python3 scripts/validate_vault.py

add-files:
	@python -m pipeline build-vault && python3 scripts/apply_tag_map.py --apply && python3 scripts/rebuild_indices.py && python3 scripts/validate_vault.py
