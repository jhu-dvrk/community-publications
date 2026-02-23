# dVRK Publications Scripts

This directory contains Python scripts for maintaining and updating the `publications.bib` file.

## Prerequisites

- Python 3.9+ 
- Virtual environment (recommended)
- `bibtexparser` library

## Installation

```zsh
# Create a virtual environment (if not already done)
python3 -m venv .venv
source .venv/bin/python  # Or .venv/Scripts/activate on Windows

# Install dependencies
pip install bibtexparser
```

## Available Scripts

### 1. `cleanup_bib.py`

This script is the main tool for maintaining the quality and consistency of the `publications.bib` file.

**What it does:**
- Normalizes all BibTeX entries with a consistent 2-space indentation.
- Standardizes field ordering (e.g., `author`, then `title`, etc.).
- Renames old `dvrk_sites` fields to the current singular `dvrk_site`.
- Cleans up excessive whitespace and newlines within fields.
- **Sorts all entries** by Year (descending) and Title (ascending).
- Ensures every field has a trailing comma to prevent corruption during future edits.

**Usage:**
```zsh
python scripts/cleanup_bib.py
```

### 2. `enrich_metadata.py` 
*(Existing script, if applicable)*
Used to fetch additional metadata for publications from online sources like Semantic Scholar.

### 3. `find_new_papers.py`
*(Existing script, if applicable)*
Used to search for new dVRK-related publications.

---
**Note:** Always verify changes in `publications.bib` before committing to Git!
