# dVRK Publications Scripts

Utility scripts for discovering, maintaining, and validating `publications.bib`.

## Setup

```zsh
# Create the virtual environment (once)
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r scripts/requirements.txt
```

## Streamlined Workflow

Routine updates require only two commands:

```zsh
# 1. Discover and interactively accept/reject new dVRK papers
#    (automatically runs update_bib.py at the end when papers are added)
python3 scripts/find_new_papers.py --start-year 2026 --end-year 2026

# 2. (Any time publications.bib is edited manually or via PR)
#    Promote published preprints, backfill tags/abstracts/citations, validate & sort
python3 scripts/update_bib.py
```

---

## Available Scripts

### `find_new_papers.py` — Discover new publications

Searches open scholarly catalogs for new dVRK / da Vinci Research Kit papers and walks through each candidate interactively (`[y]` add, `[n]` reject into `rejected_papers.json`, `[s]` skip, `[q]` quit).

| Source | API key needed? | Default behavior |
|---|---|---|
| **OpenAlex** | No | Always searched; includes abstracts and `dvrk_site` affiliations |
| **Crossref** | No | Always searched (polite pool); filters out proceedings/container records |
| **arXiv** | No | Always searched; covers preprints and open-access e-prints |
| **Semantic Scholar** | Optional | Always searched (rate-limited without key; set `SEMANTIC_SCHOLAR_API_KEY` for faster runs) |
| **IEEE Xplore** | Yes | Searched when `IEEE_API_KEY` is set |

```zsh
# Search a specific year
python3 scripts/find_new_papers.py --start-year 2026 --end-year 2026

# Search a range without auto-running update_bib.py afterward
python3 scripts/find_new_papers.py --start-year 2025 --end-year 2026 --no-update
```

---

### `update_bib.py` — Unified enrichment, cross-referencing, validation & formatting

Single idempotent maintenance pipeline for `publications.bib`:
1. **Hygiene & Fallbacks**: Normalizes months and DOIs, unescapes HTML entities in venues, sets `date_added` if missing, standardizes `@phdthesis` / `school` on theses, and ensures preprints have clean `howpublished` fallbacks.
2. **Peer-Review Classification & Preprint Promotion**: Assigns `peer_reviewed` (`yes`, `no`, or `thesis`, honoring `peer_review_overrides.json`) and checks `peer_reviewed = {no}` preprints against Crossref and OpenAlex to promote newly published journal/conference papers (enforcing title similarity verification).
3. **Incremental Affiliation, Venue & Abstract Backfill**: Queries OpenAlex (batched), Crossref, and arXiv only for entries missing `dvrk_site`, `abstract`, or venue, caching affiliation lookups in `cache/affiliation_cache.json`.
4. **Community Cross-References (`dvrk_cites`)**: Fetches Crossref reference lists for newly added DOIs (`cache/reference_cache.json`), links exact unique DOIs and unambiguous exact titles, and prunes any removed citation keys.
5. **Integrity Validation & Canonical Formatting**: Validates required fields, unique IDs/DOIs, `custom_tags.json` codes, and `dvrk_cites` targets, then writes canonically sorted, single-line-per-field BibTeX.

```zsh
# Full incremental update (recommended after manual edits or merging PRs)
python3 scripts/update_bib.py

# Preview all promotions, backfills, and citation links without modifying files
python3 scripts/update_bib.py --dry-run

# Offline formatting, sorting, cached citation linking, and validation (0 network calls)
python3 scripts/update_bib.py --offline

# Read-only validation (used in GitHub Actions CI on Pull Requests)
python3 scripts/update_bib.py --check

# Strict maintainer check (also enforces canonical sort/format and all auto-fields)
python3 scripts/update_bib.py --check --strict-format
```

---

### `deduplicate_bib.py` — Interactive duplicate review & merge

Scans `publications.bib` for entries sharing a normalized DOI or high title similarity (`≥ 0.75` by default). Merging or discarding an entry automatically redirects incoming `dvrk_cites` links to the surviving citation key.

```zsh
# Report suspected duplicates without modifying publications.bib
python3 scripts/deduplicate_bib.py --dry-run

# Interactive review ([1] keep A, [2] keep B, [m] merge, [s] skip, [q] quit)
python3 scripts/deduplicate_bib.py
```

---

### `bib_utils.py` — Shared library

Internal module providing `FIELD_ORDER`, `load_bib()`, `write_bib()`, `normalize_doi()`, `normalize_title()`, `title_similarity()`, `match_sites()`, and `load_custom_tags()` so all scripts share identical parsing and formatting rules.
