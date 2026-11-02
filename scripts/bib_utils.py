#!/usr/bin/env python3
"""
bib_utils.py
------------
Shared BibTeX parsing, canonical formatting, normalization, and schema utilities
used across the dVRK Community Publications maintenance scripts.
"""

from __future__ import annotations

import copy
import difflib
import html
import json
import os
import re
import unicodedata

import bibtexparser
from bibtexparser.bibdatabase import BibDatabase
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_BIB_PATH = os.path.join(REPO_ROOT, "publications.bib")
CUSTOM_TAGS_PATH = os.path.join(REPO_ROOT, "custom_tags.json")
PEER_REVIEW_OVERRIDES_PATH = os.path.join(REPO_ROOT, "peer_review_overrides.json")
CACHE_DIR = os.path.join(REPO_ROOT, "cache")
USER_AGENT = "dVRK-Community-Publications/2.0 (mailto:dvrk@jhu.edu)"

# Canonical BibTeX field ordering across the entire repository
FIELD_ORDER = [
    "author", "title", "journal", "booktitle", "school", "year", "volume", "number",
    "pages", "month", "publisher", "editor", "series", "collection",
    "address", "organization", "issn", "isbn",
    "doi", "url", "urldate", "ieeexplore",
    "semanticscholar", "arxiv", "arxivid", "archiveprefix", "primaryclass", "eprint",
    "pdf", "openaccesspdf", "howpublished", "pubstate", "date", "tppubtype",
    "copyright", "language",
    "research_field", "data_type", "peer_reviewed", "dvrk_site", "dvrk_cites", "date_added",
    "keywords", "abstract",
]

# Map of full/alternative month spellings -> standard 3-letter BibTeX macro
MONTH_MAP = {
    "january": "jan",  "february": "feb", "march": "mar",
    "april":   "apr",  "may":      "may", "june":  "jun",
    "july":    "jul",  "august":   "aug", "september": "sep",
    "october": "oct",  "november": "nov", "december":  "dec",
    "jan":     "jan",  "feb":      "feb", "mar":   "mar",
    "apr":     "apr",  "may":      "may", "jun":   "jun",
    "jul":     "jul",  "aug":      "aug", "sep":   "sep",
    "oct":     "oct",  "nov":      "nov", "dec":   "dec",
    "sept":    "sep",
    "1": "jan", "2": "feb",  "3": "mar", "4": "apr",
    "5": "may", "6": "jun",  "7": "jul", "8": "aug",
    "9": "sep", "10": "oct", "11": "nov", "12": "dec",
}

MONTH_NUM = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Known thesis DOI prefixes / institutional repositories
THESIS_PATTERNS = (
    "10.25560/",               # Imperial College London Spiral
    "10.7939/",                # University of Alberta Education & Research Archive
    "spiral.imperial.ac.uk",
    "etheses.whiterose.ac.uk",
    "scholaris.ca",
)

# Non-peer-reviewed preprint repositories and working-paper platforms
PREPRINT_HOSTS = (
    "arxiv",
    "biorxiv",
    "medrxiv",
    "techrxiv",
    "research square",
    "researchsquare",
    "21203/rs",
    "ssrn",
    "chemrxiv",
    "10.1101/",
    "corr",
)

# Container-level Crossref/OpenAlex types that must never be ingested as individual papers
CONTAINER_WORK_TYPES = {
    "proceedings",
    "journal",
    "journal-issue",
    "journal-volume",
    "book",
    "book-series",
    "book-set",
}

# Boilerplate journal/conference mastheads occasionally returned as abstracts by upstream APIs
MASTHEAD_RE = re.compile(
    r"(is published by the ieee|joint publication of the ieee|for membership and subscription|"
    r"international conference on intelligent robots and systems.*(?:will be held|was held)|"
    r"innovative preprint repository,\s*arxiv,\s*was created|"
    r"guest editors\s*:.*professor of|"
    r"univ\.\s*of\s*melbourne.*university\s*of\s*salerno)",
    re.IGNORECASE | re.DOTALL,
)

# Institution substring -> dVRK site acronym mapping (ordered specific -> general)
INSTITUTION_TO_SITE = {
    # USA
    "Johns Hopkins":                          "JHU",
    "Carnegie Mellon":                        "CMU",
    "Clemson University":                     "CU",
    "Clemson":                                "CU",
    "Case Western Reserve":                   "CWRU",
    "Case Western":                           "CWRU",
    "Intuitive Surgical":                     "ISS",
    "Stanford University":                    "SU",
    "Stanford":                               "SU",
    "Sheikh Zayed Institute":                 "SZIPS",
    "Children's National":                    "SZIPS",
    "SickKids":                               "SKCH",
    "Hospital for Sick Children":             "SKCH",
    "Purdue University":                      "PU",
    "Purdue":                                 "PU",
    "University of Utah":                     "UU",
    "Univ. of Utah":                          "UU",
    "University of Texas at Dallas":          "UTD",
    "UT Dallas":                              "UTD",
    "Wayne State University":                 "WSU",
    "Wayne State":                            "WSU",
    "Worcester Polytechnic Institute":        "WPI",
    "Worcester Polytechnic":                  "WPI",
    "WPI":                                    "WPI",
    "Vanderbilt University":                  "VU",
    "Vanderbilt":                             "VU",
    "UC Berkeley":                            "UCB",
    "University of California, Berkeley":     "UCB",
    "University of California Berkeley":      "UCB",
    "University of California San Diego":     "UCSD",
    "University of California, San Diego":    "UCSD",
    "UC San Diego":                           "UCSD",
    "UCSD":                                   "UCSD",
    "University of Illinois Chicago":         "UIC",
    "University of Illinois at Chicago":      "UIC",
    # Canada
    "University of Alberta":                  "UA",
    "University of British Columbia":         "UBC",
    "University of Western Ontario":          "UWO",
    "Western University":                     "UWO",
    # UK
    "Imperial College":                       "ICL",
    "The Hamlyn Centre":                      "ICL",
    "Hamlyn Centre":                          "ICL",
    "Hamlyn Center":                          "ICL",
    "University College London":              "UCL",
    "University of Leeds":                    "UL",
    # Hong Kong
    "Chinese University of Hong Kong":        "CUHK",
    "CUHK":                                   "CUHK",
    # Italy
    "Politecnico di Milano":                  "POLIMI",
    "PoliMi":                                 "POLIMI",
    "University of Turin":                    "UNITO",
    "University of Torino":                   "UNITO",
    "Università degli Studi di Torino":       "UNITO",
    "Universita degli Studi di Torino":       "UNITO",
    "Scuola Superiore Sant'Anna":             "SSSA",
    "Sant'Anna School":                       "SSSA",
    "BioRobotics Institute":                  "SSSA",
    "Biorobotics Institute":                  "SSSA",
    "Istituto di BioRobotica":                "SSSA",
    "University of Verona":                   "UV",
    "Università degli Studi di Verona":       "UV",
    "Università di Verona":                   "UV",
    "Universita di Verona":                   "UV",
    "University of Naples Federico II":       "UNFII",
    "Università degli Studi di Napoli Federico II": "UNFII",
    "Università di Napoli Federico II":       "UNFII",
    "Universita di Napoli Federico II":       "UNFII",
    # Hungary
    "Óbuda University":                       "OU",
    "Obuda University":                       "OU",
    "Óbuda":                                  "OU",
    "Obuda":                                  "OU",
    "Antal Bejczy Center":                    "OU",
    # Israel
    "Ben-Gurion University":                  "BGUN",
    "Ben Gurion University":                  "BGUN",
    "Ben-Gurion":                             "BGUN",
    "Ben Gurion":                             "BGUN",
    # South Korea
    "Seoul National University":              "SNU",
    # Germany
    "Max Planck":                             "MPI",
    "Max-Planck":                             "MPI",
    "MPI-IS":                                 "MPI",
}


def match_sites(institution_names: list[str]) -> set[str]:
    """Map a list of raw affiliation strings to known dVRK site acronyms."""
    matched: set[str] = set()
    for inst_name in institution_names or []:
        inst_lower = inst_name.lower()
        for pattern, site_id in INSTITUTION_TO_SITE.items():
            if pattern.lower() in inst_lower:
                matched.add(site_id)
                break
    return matched


def load_custom_tags(path: str = CUSTOM_TAGS_PATH) -> dict[str, set[str]]:
    """Load valid tag code sets from custom_tags.json."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {
        "research_field": {item["id"] for item in data.get("research_fields", [])},
        "data_type": {item["id"] for item in data.get("data_types", [])},
        "peer_reviewed": {item["id"] for item in data.get("peer_reviewed", [])},
        "dvrk_site": {item["id"] for item in data.get("dvrk_site", [])},
    }


def load_peer_review_overrides(path: str = PEER_REVIEW_OVERRIDES_PATH) -> dict:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"keys": {}, "venues": {}}


# ---------------------------------------------------------------------------
# Normalization & matching helpers
# ---------------------------------------------------------------------------

def normalize_doi(doi: str | None) -> str:
    """Strip URL/scheme prefixes and lowercase a DOI."""
    if not doi:
        return ""
    d = doi.strip()
    d = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", d, flags=re.IGNORECASE)
    d = re.sub(r"^doi:\s*", "", d, flags=re.IGNORECASE)
    return d.strip().lower()


def clean_doi_preserve_case(doi: str | None) -> str:
    """Strip URL/scheme prefixes from a DOI without altering case."""
    if not doi:
        return ""
    d = doi.strip()
    d = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", d, flags=re.IGNORECASE)
    d = re.sub(r"^doi:\s*", "", d, flags=re.IGNORECASE)
    return d.strip()


def normalize_title(title: str | None) -> str:
    """Fold diacritics, strip LaTeX markup/braces and punctuation, lowercase."""
    if not title:
        return ""
    s = html.unescape(title)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\\[a-zA-Z]+(?:\{[^}]*\})?", " ", s)
    s = re.sub(r"[{}]", "", s)
    s = re.sub(r"[^a-zA-Z0-9]+", " ", s.lower())
    return " ".join(s.split())


def compact_title_key(title: str | None) -> str:
    """Alphanumeric-only key for exact unambiguous citation title matching."""
    if not title:
        return ""
    t = re.sub(r"[{}\"'\\]", "", title)
    return re.sub(r"[^a-zA-Z0-9]", "", t).lower()


def title_similarity(t1: str | None, t2: str | None) -> float:
    """Fuzzy similarity ratio [0.0, 1.0] between two normalized titles."""
    n1, n2 = normalize_title(t1), normalize_title(t2)
    if not n1 or not n2:
        return 0.0
    return difflib.SequenceMatcher(None, n1, n2).ratio()


def extract_surnames(author_str: str | None) -> set[str]:
    """Extract normalized surname tokens from a BibTeX 'and'-delimited author string."""
    surnames: set[str] = set()
    if not author_str:
        return surnames
    for raw in re.split(r"\s+and\s+", author_str, flags=re.IGNORECASE):
        raw = re.sub(r"[{}]", "", raw).strip()
        if not raw:
            continue
        if "," in raw:
            last = raw.split(",")[0].strip()
        else:
            parts = raw.split()
            last = parts[-1] if parts else ""
        nl = normalize_title(last)
        if nl:
            for token in nl.split():
                if len(token) >= 2:
                    surnames.add(token)
            surnames.add(nl.replace(" ", ""))
    return surnames


def extract_arxiv_id(entry_or_str: dict | str | None) -> str | None:
    """Safely extract an arXiv ID (YYMM.NNNN or YYMM.NNNNN) without matching conference DOIs."""
    if not entry_or_str:
        return None
    if isinstance(entry_or_str, str):
        m = re.search(
            r"(?:arxiv\.org/(?:abs|pdf)/|arxiv:\s*|/arxiv\.)(\d{4}\.\d{4,5})(?:v\d+)?",
            entry_or_str,
            re.IGNORECASE,
        )
        if m:
            return m.group(1)
        if re.match(r"^\d{4}\.\d{4,5}(?:v\d+)?$", entry_or_str.strip()):
            return entry_or_str.strip().split("v")[0]
        return None

    for field in ("eprint", "arxivid", "arxiv", "doi", "url", "howpublished", "journal", "booktitle"):
        val = entry_or_str.get(field, "")
        if not val:
            continue
        if field in ("eprint", "arxivid") and re.match(r"^\d{4}\.\d{4,5}(?:v\d+)?$", val.strip()):
            return val.strip().split("v")[0]
        aid = extract_arxiv_id(val)
        if aid:
            return aid
    return None


def clean_abstract_text(text: str | None) -> str:
    """Strip HTML tags/entities, leading 'Abstract:' prefixes, and extra whitespace."""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"^\s*abstract[\s:.\-—]+", "", text, flags=re.IGNORECASE)
    return " ".join(text.split()).strip()


def reconstruct_openalex_abstract(inverted_index: dict | None) -> str:
    """Reconstruct plaintext abstract from an OpenAlex abstract_inverted_index."""
    if not isinstance(inverted_index, dict) or not inverted_index:
        return ""
    pos_map: dict[int, str] = {}
    for word, positions in inverted_index.items():
        if not isinstance(positions, list):
            continue
        for pos in positions:
            if isinstance(pos, int):
                pos_map[pos] = word
    if not pos_map:
        return ""
    text = " ".join(pos_map[i] for i in sorted(pos_map))
    return clean_abstract_text(text)


# ---------------------------------------------------------------------------
# BibTeX parsing, date sorting & canonical writer
# ---------------------------------------------------------------------------

def extract_pub_date(entry: dict) -> tuple[int, int, int]:
    """Extract (year, month, day) integers for chronological sorting."""
    year_str = entry.get("year", "0").strip()
    try:
        year = int(year_str)
    except ValueError:
        year = 9999 if year_str.lower() == "to appear" else 0

    month = 0
    day = 0

    raw_month = entry.get("month", "").strip().strip('{}"\' ').lower()
    if raw_month:
        m_code = MONTH_MAP.get(raw_month, raw_month)
        if m_code in MONTH_NUM:
            month = MONTH_NUM[m_code]

    raw_date = entry.get("date", "").strip().strip('{}"\' ')
    if raw_date:
        parts = raw_date.split("-")
        if len(parts) >= 2 and month == 0:
            try:
                month = int(parts[1])
            except ValueError:
                pass
        if len(parts) >= 3 and day == 0:
            try:
                day = int(parts[2])
            except ValueError:
                pass

    return (year, month, day)


def normalize_months(content: str) -> str:
    """Normalize bare/full month names to braced 3-letter BibTeX macros."""
    def _replace(m: re.Match) -> str:
        raw = m.group(1).strip().strip('{}"\' ')
        normalized = MONTH_MAP.get(raw.lower())
        if normalized:
            return f"month = {{{normalized}}}"
        return f"month = {{{raw}}}"

    return re.sub(
        r"month\s*=\s*(\{?[^,\}\n]+\}?)",
        _replace,
        content,
        flags=re.IGNORECASE,
    )


def enforce_one_field_per_line(content: str) -> str:
    """Join multi-line field values so every BibTeX field occupies a single line."""
    field_re = re.compile(r"^\s+[\w][\w\-]*\s*=")
    entry_re = re.compile(r"^@")
    close_re = re.compile(r"^\s*\}")

    lines = content.split("\n")
    out: list[str] = []
    depth = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            out.append(line)
            depth = 0
            continue

        is_new_field = bool(field_re.match(line))
        is_entry_start = bool(entry_re.match(line))
        is_entry_close = bool(close_re.match(line))

        if depth > 0 and not is_new_field and not is_entry_start and not is_entry_close:
            out[-1] = out[-1].rstrip() + " " + stripped
        else:
            out.append(line)
            depth = 0

        unescaped = re.sub(r"\\[{}]", "", (stripped if depth > 0 else line))
        depth += unescaped.count("{") - unescaped.count("}")
        depth = max(depth, 0)

    return "\n".join(out)


def load_bib(path: str = DEFAULT_BIB_PATH) -> BibDatabase:
    """Parse a BibTeX file safely after normalizing month fields."""
    parser = BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False
    with open(path, "r", encoding="utf-8") as f:
        raw_content = normalize_months(f.read())
    return bibtexparser.loads(raw_content, parser=parser)


def sort_entry_key(entry: dict) -> tuple:
    y, m, d = extract_pub_date(entry)
    return (-y, -m, -d, entry.get("title", "").lower(), entry.get("ID", "").lower())


def format_bib_string(bib_db: BibDatabase, sort: bool = True) -> str:
    """Format a BibDatabase into canonical sorted, single-line-per-field BibTeX text."""
    db_copy = BibDatabase()
    db_copy.entries = [copy.copy(e) for e in bib_db.entries]

    for entry in db_copy.entries:
        for field, val in list(entry.items()):
            if isinstance(val, str):
                cleaned = val.replace("\n", " ").strip()
                while "  " in cleaned:
                    cleaned = cleaned.replace("  ", " ")
                entry[field] = cleaned

    if sort:
        db_copy.entries.sort(key=sort_entry_key)

    writer = BibTexWriter()
    writer.indent = "  "
    writer.order_entries_by = None
    writer.display_order = FIELD_ORDER
    writer.add_trailing_comma = True

    return enforce_one_field_per_line(writer.write(db_copy))


def write_bib(path: str, bib_db: BibDatabase, sort: bool = True) -> None:
    """Write a BibDatabase to disk in canonical sorted format."""
    output = format_bib_string(bib_db, sort=sort)
    with open(path, "w", encoding="utf-8") as f:
        f.write(output)


def redirect_or_prune_cites(entries: list[dict], merged_map: dict[str, str] | None = None) -> int:
    """Redirect merged citation keys and prune missing or self-citing keys from dvrk_cites."""
    merged_map = merged_map or {}
    valid_ids = {e["ID"] for e in entries}
    changed_links = 0

    for entry in entries:
        raw_cites = entry.get("dvrk_cites", "").strip()
        if not raw_cites:
            continue
        orig = [c.strip() for c in raw_cites.split(" and ") if c.strip()]
        updated: list[str] = []
        for c in orig:
            target = merged_map.get(c, c)
            if target in valid_ids and target != entry["ID"] and target not in updated:
                updated.append(target)
        updated_sorted = sorted(updated)
        if updated_sorted != orig:
            changed_links += abs(len(orig) - len(updated_sorted)) or 1
        if updated_sorted:
            entry["dvrk_cites"] = " and ".join(updated_sorted)
        else:
            del entry["dvrk_cites"]

    return changed_links
