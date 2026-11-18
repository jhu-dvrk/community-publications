---
name: update-publications
description: >-
  Discovers, verifies, and adds new dVRK and dVRK-Si publications and promotes
  newly published preprints in publications.bib. Use when the user asks to
  check for new publications, update the publication list, or check preprints.
---

# Updating dVRK Community Publications

Follow this workflow when checking for newly published preprints and new dVRK publications.

## 1. Check Existing Preprints for Promotion
1. Inspect entries in `publications.bib` with `peer_reviewed = {no}`.
2. Run `./.venv/bin/python -u scripts/update_bib.py --dry-run` and check arXiv `doi` / `journal_ref` fields, Crossref, OpenAlex, DBLP, and recent conference proceedings (such as `papers.miccai.org` inline BibTeX) for newly assigned archival DOIs.
3. Verify title similarity (`>= 0.75`) and shared author surnames before promoting any preprint to `peer_reviewed = {yes}`, preserving `arxiv` links.

## 2. Multi-Source Candidate Discovery
Query across the full target year(s) — IEEE Xplore and Springer often index summer conference proceedings (`ICRA`, `BioRob`, `INES`, `IROS`, `MICCAI`) months later while stamping `publication_date` with the earlier conference month:
- **OpenAlex**: Query `title_and_abstract.search` (`"da Vinci Research Kit"`, `dVRK`, and known dataset names from `dvrk_dataset` entries such as `SurgRIPE`, `SurgPose`, `ROSMA`, `LUMICS`, `MV-dVRK`, `SurgSync`, `ImitateCholec`, `Open-H-Embodiment`), `fulltext.search`, and forward citations (`cites:W2047152546|W3156235920`, plus forward citations of `dvrk_dataset` creator papers) across the full year, filtering out existing DOIs/normalized titles in **both** `publications.bib` and `dataset_publications.bib`, and `rejected_papers.json`.
- **Crossref & DBLP**: Query `"da Vinci Research Kit"` and `"dVRK"`, ignoring container types (`proceedings`, `journal-issue`).
- **arXiv**: Search `all:dVRK`, `all:"da Vinci Research Kit"`, and specific `dvrk_dataset` names sorted by `submittedDate`.

## 3. Full-Text Experimental Verification ("Made Possible by dVRK")
For every candidate not already explicitly confirmed in its abstract:
1. Inspect the Methods / Experimental Setup section via `https://arxiv.org/html/<id>`, raw LaTeX tarballs at `https://arxiv.org/e-print/<id>` (for brand-new arXiv submissions without HTML), publisher landing pages, or Europe PMC `fullTextXML`.
2. **Accept & Route**:
   - **Core (`publications.bib`)**: Direct dVRK/dVRK-Si hardware, dVRK software/simulators (AMBF, SurRoL, dVRL, Orbit-Surgical, CoppeliaSim dVRK), dVRK-focused reviews, **dataset-creating papers** (tag with `dvrk_dataset = {<Name>}` iff the paper introduces the dataset), or papers using **both** dVRK/simulators and a dataset.
   - **Dataset-only (`dataset_publications.bib`)**: Papers that *only* train/benchmark on dVRK-acquired datasets (e.g., SurgRIPE, SurgPose, ROSMA, Open-H, CRCD, LUMICS, MV-dVRK) without dVRK hardware/software/simulators. Use `datasets = {<CreatorBibID1> and <CreatorBibID2>}` instead of `research_field`/`data_type`/`dvrk_site`/`dvrk_cites`. Never place the same paper in both `.bib` files.
3. **Reject** papers that only cite dVRK in Related Work, use unrelated manipulators (UR5, KUKA, Franka) or clinical-only videos, or are general clinical/robotics reviews — even if co-authored by dVRK labs. Append rejected candidates (`{"doi": ..., "title": ...}`) to `rejected_papers.json` so future runs skip them.
4. Check fuzzy title similarity and author overlap against all existing entries in both `publications.bib` and `dataset_publications.bib` to avoid duplicating an existing preprint or published paper.

## 4. Enrich, Cross-Reference & Validate
1. Add verified entries with canonical `Last, First` authors, braced title acronyms, LaTeX/HTML-free abstracts, valid `custom_tags.json` codes, and `date_added = {YYYY-MM-DD}`.
2. If adding a dissertation from a new university repository DOI prefix, add the prefix to `THESIS_PATTERNS` in `scripts/bib_utils.py`.
3. Run `./.venv/bin/python -u scripts/update_bib.py` to backfill `dvrk_cites` (via Crossref, OpenAlex, and arXiv HTML bibliographies) and canonically sort `publications.bib`.
4. Run `./.venv/bin/python scripts/update_bib.py --check --strict-format` and confirm `0` errors and `0` advisories.

