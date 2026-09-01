#!/usr/bin/env python3
"""Backfill only missing BibTeX abstracts from the OpenAlex API.

The script deliberately leaves every other field untouched. It resolves DOIs
in batches, then performs strict title, author, and year matching for records
that remain. Only results with an OpenAlex abstract inverted index are used.
"""

import argparse
import difflib
import json
import re
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

import requests


API_BASE = "https://api.openalex.org"
SELECT_FIELDS = (
    "id,doi,display_name,publication_year,authorships,abstract_inverted_index"
)
DOI_BATCH_SIZE = 40
TIMEOUT_SECONDS = 30
REQUEST_DELAY_SECONDS = 0.15


def normalize_title(value):
    """Normalize titles enough to make source matching resilient to markup."""
    value = unicodedata.normalize("NFKD", value)
    value = re.sub(r"[{}]", "", value)
    value = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return " ".join(value.split())


def title_similarity(left, right):
    return difflib.SequenceMatcher(
        None, normalize_title(left), normalize_title(right)
    ).ratio()


def normalize_doi(value):
    value = value.strip().lower()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value)
    return value


def normalize_arxiv(value):
    value = value.strip()
    match = re.search(r"(\d{4}\.\d{4,5})(?:v\d+)?", value)
    return match.group(1) if match else value.lower()


def read_braced_field(block, field):
    """Return a braced BibTeX field and its content bounds, if present."""
    match = re.search(rf"(?im)^\s*{re.escape(field)}\s*=\s*\{{", block)
    if not match:
        return None

    start = match.end()
    depth = 1
    index = start
    while index < len(block):
        character = block[index]
        if character == "\\":
            index += 2
            continue
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return block[start:index].strip(), start, index
        index += 1
    return None


def parse_missing_abstracts(content):
    records = []
    for index, block in enumerate(re.split(r"(?m)(?=^@)", content)):
        if not block.startswith("@"):
            continue
        identifier_match = re.match(r"^@[A-Za-z]+\{([^,\s]+)", block)
        if not identifier_match:
            continue
        abstract = read_braced_field(block, "abstract")
        if abstract and abstract[0]:
            continue

        def field_value(name):
            value = read_braced_field(block, name)
            return value[0] if value else ""

        title = field_value("title")
        if not title:
            continue
        records.append(
            {
                "block_index": index,
                "id": identifier_match.group(1),
                "title": title,
                "doi": field_value("doi"),
                "arxiv": field_value("arxiv"),
                "author": field_value("author"),
                "year": field_value("year"),
            }
        )
    return records


def request_json(path, *, params=None):
    """Request JSON with bounded retries for transient API failures."""
    request_headers = {"User-Agent": "dVRK-Community-Publications/1.0"}

    for attempt in range(4):
        try:
            response = requests.get(
                f"{API_BASE}{path}",
                params=params,
                headers=request_headers,
                timeout=TIMEOUT_SECONDS,
            )
        except requests.RequestException as error:
            if attempt == 3:
                return None, f"request error: {error}"
            time.sleep(2 ** attempt)
            continue

        if response.status_code == 200:
            return response.json(), None
        if response.status_code in {429, 500, 502, 503, 504} and attempt < 3:
            retry_after = response.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else 2 ** (attempt + 1)
            time.sleep(delay)
            continue
        return None, f"HTTP {response.status_code}: {response.text[:200]}"

    return None, "retry budget exhausted"


def reconstruct_abstract(index):
    """Turn OpenAlex's inverted abstract index into verified plaintext."""
    if not isinstance(index, dict) or not index:
        return None
    words = {}
    for word, positions in index.items():
        if not isinstance(positions, list):
            return None
        for position in positions:
            if not isinstance(position, int) or position in words:
                return None
            words[position] = word
    if not words or sorted(words) != list(range(len(words))):
        return None
    return " ".join(words[position] for position in range(len(words)))


def candidate_from_work(work):
    return {
        "id": work.get("id", ""),
        "doi": work.get("doi", ""),
        "title": work.get("display_name", ""),
        "year": work.get("publication_year"),
        "authors": [
            authorship.get("author", {}).get("display_name", "")
            for authorship in work.get("authorships", [])
        ],
        "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
    }


def surname(value):
    value = value.split(" and ", 1)[0].strip()
    if "," in value:
        value = value.split(",", 1)[0]
    else:
        value = value.split()[-1] if value.split() else ""
    value = unicodedata.normalize("NFKD", value)
    return re.sub(r"[^a-z0-9]", "", value.lower())


def title_candidate_matches(record, candidate):
    """Require a near-exact title plus compatible author and year metadata."""
    score = title_similarity(record["title"], candidate["title"])
    if score < 0.97:
        return False, score

    if record["year"].isdigit() and isinstance(candidate["year"], int):
        if abs(int(record["year"]) - candidate["year"]) > 1:
            return False, score

    expected_surname = surname(record["author"])
    candidate_surnames = {surname(author) for author in candidate["authors"] if author}
    if expected_surname and candidate_surnames and expected_surname not in candidate_surnames:
        return False, score
    return True, score


def doi_candidate_matches(record, candidate):
    if normalize_doi(record["doi"]) != normalize_doi(candidate["doi"]):
        return False, 0.0
    score = title_similarity(record["title"], candidate["title"])
    return score >= 0.84, score


def escape_bibtex(value):
    value = " ".join(value.split())
    return value.replace("{", r"\{").replace("}", r"\}")


def insert_or_replace_abstract(block, abstract):
    encoded = escape_bibtex(abstract)
    field = read_braced_field(block, "abstract")
    if field:
        _, start, end = field
        return block[:start] + encoded + block[end:]

    closing = block.rfind("}")
    if closing == -1:
        raise ValueError("BibTeX entry has no closing brace")
    prefix = block[:closing].rstrip()
    if not prefix.endswith(","):
        prefix += ","
    return prefix + f"\n  abstract = {{{encoded}}},\n" + block[closing:]


def apply_updates(path, updates):
    content = path.read_text(encoding="utf-8")
    blocks = re.split(r"(?m)(?=^@)", content)
    applied = set()
    for index, block in enumerate(blocks):
        if not block.startswith("@"):
            continue
        identifier_match = re.match(r"^@[A-Za-z]+\{([^,\s]+)", block)
        if not identifier_match:
            continue
        identifier = identifier_match.group(1)
        if identifier in updates:
            blocks[index] = insert_or_replace_abstract(block, updates[identifier])
            applied.add(identifier)

    if applied != set(updates):
        missing = ", ".join(sorted(set(updates) - applied))
        raise ValueError(f"Could not locate entries for: {missing}")

    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as temporary:
        temporary.write("".join(blocks))
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def retrieve_doi_matches(records, updates, details, errors):
    """Retrieve DOI-bearing works in exact-match OpenAlex batches."""
    grouped = {}
    for record in records:
        if record["doi"]:
            grouped.setdefault(normalize_doi(record["doi"]), []).append(record)

    dois = list(grouped)
    for start in range(0, len(dois), DOI_BATCH_SIZE):
        batch = dois[start : start + DOI_BATCH_SIZE]
        data, error = request_json(
            "/works",
            params={
                "filter": "doi:" + "|".join(batch),
                "per-page": DOI_BATCH_SIZE,
                "select": SELECT_FIELDS,
            },
        )
        if error:
            errors.append(f"DOI batch {start // DOI_BATCH_SIZE + 1}: {error}")
            continue

        works = {
            normalize_doi(work.get("doi", "")): candidate_from_work(work)
            for work in (data or {}).get("results", [])
        }
        for doi in batch:
            candidate = works.get(doi)
            if not candidate or not candidate["abstract"]:
                continue
            for record in grouped[doi]:
                matches, score = doi_candidate_matches(record, candidate)
                if matches:
                    updates[record["id"]] = candidate["abstract"]
                    details[record["id"]] = {
                        "source": "doi",
                        "openalex_id": candidate["id"],
                        "title_score": round(score, 4),
                    }
        if start + DOI_BATCH_SIZE < len(dois):
            time.sleep(REQUEST_DELAY_SECONDS)


def retrieve_title_matches(records, updates, details, errors, max_searches):
    """Search unresolved records and accept only strict title matches."""
    unresolved = [record for record in records if record["id"] not in updates]
    if max_searches is not None:
        unresolved = unresolved[:max_searches]
    for position, record in enumerate(unresolved, 1):
        data, error = request_json(
            "/works",
            params={
                # OpenAlex treats literal * and ? as wildcard syntax.
                "search": re.sub(r"[*?]", " ", record["title"]),
                "per-page": 10,
                "select": SELECT_FIELDS,
            },
        )
        if error:
            errors.append(f"{record['id']}: {error}")
            continue

        candidates = [
            candidate_from_work(work) for work in (data or {}).get("results", [])
        ]
        candidates.sort(
            key=lambda candidate: title_similarity(record["title"], candidate["title"]),
            reverse=True,
        )
        for candidate in candidates:
            if not candidate["abstract"]:
                continue
            matches, score = title_candidate_matches(record, candidate)
            if matches:
                updates[record["id"]] = candidate["abstract"]
                details[record["id"]] = {
                    "source": "title",
                    "openalex_id": candidate["id"],
                    "title_score": round(score, 4),
                }
                break

        if position % 10 == 0 or position == len(unresolved):
            print(f"Title fallback: {position}/{len(unresolved)}", flush=True)
        if position < len(unresolved):
            time.sleep(REQUEST_DELAY_SECONDS)


def main():
    parser = argparse.ArgumentParser(
        description="Backfill only missing abstracts from OpenAlex."
    )
    parser.add_argument("file", nargs="?", default="publications.bib")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write validated abstract additions to the BibTeX file.",
    )
    parser.add_argument(
        "--report",
        help="Optional path for a JSON report without abstract text.",
    )
    parser.add_argument(
        "--skip-title-search",
        action="store_true",
        help="Apply only exact DOI matches without spending title-search quota.",
    )
    parser.add_argument(
        "--max-title-searches",
        type=int,
        default=80,
        help=(
            "Maximum strict title searches per run (default: 80, "
            "below the anonymous OpenAlex search allowance)."
        ),
    )
    args = parser.parse_args()

    path = Path(args.file)
    content = path.read_text(encoding="utf-8")
    records = parse_missing_abstracts(content)
    updates = {}
    details = {}
    errors = []

    retrieve_doi_matches(records, updates, details, errors)
    if not args.skip_title_search:
        retrieve_title_matches(
            records, updates, details, errors, args.max_title_searches
        )

    report = {
        "missing_before": len(records),
        "retrieved": len(updates),
        "doi_matches": sum(
            detail["source"] == "doi" for detail in details.values()
        ),
        "title_matches": sum(
            detail["source"] == "title" for detail in details.values()
        ),
        "matches": details,
        "unresolved": sorted(record["id"] for record in records if record["id"] not in updates),
        "errors": errors,
    }
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.apply and updates:
        apply_updates(path, updates)

    action = "Applied" if args.apply else "Would apply"
    print(
        f"{action} {report['retrieved']} abstracts "
        f"({report['doi_matches']} DOI, {report['title_matches']} title matches); "
        f"{len(report['unresolved'])} remain unresolved.",
        flush=True,
    )
    if errors:
        print(f"{len(errors)} API request(s) failed; see the report for details.", file=sys.stderr)


if __name__ == "__main__":
    main()
