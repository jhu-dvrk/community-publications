#!/usr/bin/env python3
"""
Search for new dVRK / da Vinci Research Kit publications and interactively
add them to publications.bib.

Search sources (tried in order, all free):
  1. CrossRef       — covers most published journals and conference papers
  2. arXiv          — covers preprints and many open-access papers
  3. Semantic Scholar — works best with an API key; heavily rate-limited otherwise

BibTeX is fetched from doi.org via content negotiation for the best quality.

Usage:
    python3 scripts/find_new_papers.py --start-year 2026 --end-year 2026

Optional environment variables:
    SEMANTIC_SCHOLAR_API_KEY   — enables reliable Semantic Scholar search
    IEEE_API_KEY               — enables IEEE Xplore search
"""

import argparse
import os
import json
import sys
import time
import webbrowser
import xml.etree.ElementTree as ET
import urllib.parse

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SEMANTIC_SCHOLAR_API_KEY = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
IEEE_API_KEY = os.environ.get("IEEE_API_KEY", "")
REJECTED_FILE = "rejected_papers.json"
CROSSREF_MAILTO = "dvrk@jhu.edu"   # Polite-pool access; CrossRef asks for this


# ---------------------------------------------------------------------------
# BibTeX file helpers
# ---------------------------------------------------------------------------

def load_existing_data(bib_path):
    """Return (set of DOIs, set of titles) already in the bib file."""
    dois, titles = set(), set()
    try:
        with open(bib_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.lower().startswith(("doi =", "doi=")):
                    v = line.split("=", 1)[1].strip().strip(",").strip('"').strip("{}")
                    dois.add(v.lower())
                elif line.lower().startswith(("title =", "title=")):
                    v = line.split("=", 1)[1].strip().strip(",").strip('"').strip("{}")
                    titles.add(v.lower())
    except Exception as e:
        print(f"Error reading bib file: {e}")
    return dois, titles


def load_rejected_dois(rejected_path):
    """Return a set of rejected DOIs/titles."""
    items = set()
    if os.path.exists(rejected_path):
        try:
            with open(rejected_path) as f:
                for item in json.load(f):
                    if item.get("doi"):
                        items.add(item["doi"].lower())
                    if item.get("title"):
                        items.add(item["title"].lower())
        except Exception as e:
            print(f"Error reading rejected file: {e}")
    return items


def save_rejected(paper, rejected_path):
    lst = []
    if os.path.exists(rejected_path):
        try:
            with open(rejected_path) as f:
                lst = json.load(f)
        except Exception:
            pass
    entry = {"doi": paper.get("doi"), "title": paper.get("title")}
    if entry not in lst:
        lst.append(entry)
    with open(rejected_path, "w") as f:
        json.dump(lst, f, indent=2)


def append_to_bib(paper, bib_path):
    """Append a paper's BibTeX block to the bib file, injecting custom fields."""
    if not paper.get("bibtex"):
        print("  Cannot add: no BibTeX available.")
        return False
    try:
        bib_block = paper["bibtex"].strip()
        if bib_block.endswith("}"):
            bib_block = bib_block[:-1]  # strip closing brace
            # Inject custom / extra fields
            if paper.get("url"):
                bib_block += f",\n  url = {{{paper['url']}}}"
            if paper.get("semanticscholar"):
                bib_block += f",\n  semanticscholar = {{{paper['semanticscholar']}}}"
            if paper.get("ieeexplore"):
                bib_block += f",\n  ieeexplore = {{{paper['ieeexplore']}}}"
            if paper.get("arxiv"):
                bib_block += f",\n  arxiv = {{{paper['arxiv']}}}"
            bib_block += "\n}\n"
        with open(bib_path, "a", encoding="utf-8") as f:
            f.write("\n")
            f.write(bib_block)
            f.write("\n")
        print(f"  ✅ Added: {paper['title']}")
        return True
    except Exception as e:
        print(f"  Error appending to bib: {e}")
        return False


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def fetch_with_retry(url, params=None, headers=None, retries=3, delay=5):
    """GET with retry on rate-limit (429) or transient server errors."""
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=15)
            if r.status_code == 200:
                return r
            elif r.status_code == 429:
                wait = delay * (2 ** attempt)
                print(f"  Rate limited. Waiting {wait}s (attempt {attempt + 1}/{retries})...")
                time.sleep(wait)
            elif 500 <= r.status_code < 600:
                print(f"  Server error {r.status_code}, retrying...")
                time.sleep(delay)
            else:
                print(f"  HTTP {r.status_code}: {r.text[:200]}")
                break
        except Exception as e:
            print(f"  Request error: {e}")
            time.sleep(delay)
    return None


# ---------------------------------------------------------------------------
# BibTeX fetching
# ---------------------------------------------------------------------------

def doi_to_bibtex(doi):
    """Fetch a proper BibTeX entry from doi.org via content negotiation."""
    r = fetch_with_retry(
        f"https://doi.org/{doi}",
        headers={"Accept": "application/x-bibtex"},
    )
    if r and r.status_code == 200 and r.text.strip().startswith("@"):
        return r.text.strip()
    return None


# ---------------------------------------------------------------------------
# Source 1: CrossRef
# ---------------------------------------------------------------------------

def _is_crossref_relevant(title, venue, query):
    """
    Return True if a CrossRef result is genuinely related to the query.

    CrossRef full-text search is broad: querying 'da Vinci Research Kit'
    also returns Leonardo da Vinci art history papers. We post-filter by
    requiring the title or venue to contain at least one dVRK-specific term.
    """
    REQUIRED_TERMS = [
        "dvrk", "da vinci research kit",
        "surgical robot", "robotic surgery", "surgical manipulator",
        "laparoscop", "endoscop", "teleoperat", "haptic",
        "patient side manipulator", "psm", "ecm", "mtm",
    ]
    combined = (title + " " + venue).lower()
    return any(term in combined for term in REQUIRED_TERMS)


def search_crossref(query, start_year, end_year, existing_dois, existing_titles, rejected_dois):
    """
    Search CrossRef for papers matching *query* published between start_year
    and end_year.  No API key required; uses the polite pool via mailto.
    Results are post-filtered for relevance to avoid art/history false positives.
    """
    url = "https://api.crossref.org/works"
    params = {
        "query": query,
        "filter": f"from-pub-date:{start_year}-01,until-pub-date:{end_year}-12",
        "rows": 100,
        "select": "DOI,title,author,published,container-title,type,URL",
        "mailto": CROSSREF_MAILTO,
    }
    print(f"Searching CrossRef for '{query}' ({start_year}–{end_year})...")
    r = fetch_with_retry(url, params=params)
    if not r:
        return []

    items = r.json().get("message", {}).get("items", [])
    print(f"  -> {len(items)} raw results (filtering for relevance...)")
    new_papers = []
    for item in items:
        doi = item.get("DOI", "")
        title_parts = item.get("title", [])
        title = title_parts[0] if title_parts else ""
        if not title:
            continue

        # Skip already-known
        if doi and doi.lower() in existing_dois:
            continue
        if title.lower() in existing_titles:
            continue
        if doi and doi.lower() in rejected_dois:
            continue
        if title.lower() in rejected_dois:
            continue

        # Venue (needed for relevance check)
        container = item.get("container-title", [])
        venue = container[0] if container else ""

        # Relevance filter — discard art-history / unrelated "da Vinci" hits
        if not _is_crossref_relevant(title, venue, query):
            continue

        authors = [
            f"{a.get('given', '')} {a.get('family', '')}".strip()
            for a in item.get("author", [])
        ]

        # Year
        pub = item.get("published", {}).get("date-parts", [[None]])[0]
        year = pub[0] if pub else None


        new_papers.append({
            "source": "CrossRef",
            "title": title,
            "year": year,
            "authors": authors,
            "doi": doi,
            "venue": venue,
            "bibtex": None,      # fetched later via doi.org
            "semanticscholar": None,
            "ieeexplore": None,
            "arxiv": None,
            "url": item.get("URL"),
        })
    return new_papers


# ---------------------------------------------------------------------------
# Source 2: arXiv
# ---------------------------------------------------------------------------

def search_arxiv(query, start_year, end_year, existing_dois, existing_titles, rejected_dois):
    """
    Search arXiv for papers whose title/abstract contains *query*,
    submitted between start_year and end_year.  No API key required.
    """
    encoded_query = urllib.parse.quote(f'all:"{query}"')
    # arXiv date format for submittedDate: YYYYMMDDHHMMSS
    date_from = f"{start_year}01010000"
    date_to   = f"{end_year}12312359"
    url = (
        f"https://export.arxiv.org/api/query"
        f"?search_query={encoded_query}"
        f"+AND+submittedDate:[{date_from}+TO+{date_to}]"
        f"&start=0&max_results=100&sortBy=submittedDate&sortOrder=descending"
    )
    print(f"Searching arXiv for '{query}' ({start_year}–{end_year})...")
    r = fetch_with_retry(url)
    if not r:
        return []

    ns = {
        "a": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    try:
        root = ET.fromstring(r.text)
    except ET.ParseError as e:
        print(f"  arXiv XML parse error: {e}")
        return []

    entries = root.findall("a:entry", ns)
    print(f"  -> {len(entries)} results")
    new_papers = []
    for entry in entries:
        title_el = entry.find("a:title", ns)
        title = title_el.text.strip().replace("\n", " ") if title_el is not None else ""
        if not title:
            continue

        # arXiv ID
        id_el = entry.find("a:id", ns)
        arxiv_id = id_el.text.strip().split("/abs/")[-1] if id_el is not None else ""
        arxiv_url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else None

        # DOI (if published)
        doi_el = entry.find("arxiv:doi", ns)
        doi = doi_el.text.strip() if doi_el is not None else None

        # Year
        pub_el = entry.find("a:published", ns)
        year = int(pub_el.text[:4]) if pub_el is not None else None

        if doi and doi.lower() in existing_dois:
            continue
        if title.lower() in existing_titles:
            continue
        if doi and doi.lower() in rejected_dois:
            continue
        if title.lower() in rejected_dois:
            continue

        authors = [
            n.text.strip()
            for a in entry.findall("a:author", ns)
            for n in a.findall("a:name", ns)
        ]

        # Build minimal BibTeX for arXiv preprints (doi.org takes over if DOI found)
        key = (authors[0].split()[-1] if authors else "Unknown") + str(year or "") + title.split()[0].lower().strip(":")
        bib_lines = [
            f"@misc{{{key},",
            f"  author = {{{' and '.join(authors)}}},",
            f"  title  = {{{title}}},",
            f"  year   = {{{year}}},",
        ]
        if arxiv_url:
            bib_lines.append(f"  howpublished = {{\\url{{{arxiv_url}}}}},")
        bib_lines.append("}")
        fallback_bibtex = "\n".join(bib_lines)

        new_papers.append({
            "source": "arXiv",
            "title": title,
            "year": year,
            "authors": authors,
            "doi": doi,
            "bibtex": fallback_bibtex,  # overwritten below if DOI found
            "semanticscholar": None,
            "ieeexplore": None,
            "arxiv": arxiv_url,
            "url": None,
        })
    return new_papers


# ---------------------------------------------------------------------------
# Source 3: Semantic Scholar (optional — much better with API key)
# ---------------------------------------------------------------------------

def search_semantic_scholar(query, years, existing_dois, existing_titles, rejected_dois):
    year_range = f"{years[0]}-{years[-1]}"
    print(f"Searching Semantic Scholar for '{query}' in {year_range}...")

    headers = {}
    if SEMANTIC_SCHOLAR_API_KEY:
        headers["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY
    else:
        print("  (no API key — may be rate-limited; set SEMANTIC_SCHOLAR_API_KEY to avoid this)")

    params = {
        "query": query,
        "year": year_range,
        "fields": "title,authors,year,journal,venue,publicationVenue,externalIds,citationStyles,url",
        "limit": 100,
    }
    r = fetch_with_retry(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        params=params,
        headers=headers,
    )
    if not r:
        return []

    new_papers = []
    for paper in r.json().get("data", []):
        doi   = (paper.get("externalIds") or {}).get("DOI")
        title = paper.get("title", "") or ""
        if doi and doi.lower() in existing_dois:
            continue
        if title.lower() in existing_titles:
            continue
        if doi and doi.lower() in rejected_dois:
            continue
        if title.lower() in rejected_dois:
            continue

        new_papers.append({
            "source": "Semantic Scholar",
            "title": title,
            "year": paper.get("year"),
            "authors": [a.get("name") for a in paper.get("authors", [])],
            "doi": doi,
            "bibtex": (paper.get("citationStyles") or {}).get("bibtex"),
            "semanticscholar": paper.get("url"),
            "ieeexplore": None,
            "arxiv": (
                f"https://arxiv.org/abs/{paper['externalIds']['ArXiv']}"
                if (paper.get("externalIds") or {}).get("ArXiv") else None
            ),
            "url": None,
        })
    print(f"  -> {len(new_papers)} new results")
    return new_papers


# ---------------------------------------------------------------------------
# Source 4: IEEE Xplore (requires API key)
# ---------------------------------------------------------------------------

def search_ieee_xplore(query, start_year, end_year, existing_dois, existing_titles, rejected_dois):
    if not IEEE_API_KEY:
        print("Skipping IEEE Xplore search: set IEEE_API_KEY to enable.")
        return []

    print(f"Searching IEEE Xplore for '{query}' ({start_year}–{end_year})...")
    params = {
        "apikey": IEEE_API_KEY,
        "format": "json",
        "max_records": 100,
        "start_year": start_year,
        "end_year": end_year,
        "querytext": query,
    }
    r = fetch_with_retry("http://ieeexploreapi.ieee.org/api/v1/search/articles", params=params)
    if not r:
        return []

    new_papers = []
    for article in r.json().get("articles", []):
        doi   = article.get("doi")
        title = article.get("title", "")
        if doi and doi.lower() in existing_dois:
            continue
        if title.lower() in existing_titles:
            continue
        if doi and doi.lower() in rejected_dois:
            continue
        if title.lower() in rejected_dois:
            continue

        authors = [
            a.get("full_name", "")
            for a in (article.get("authors") or {}).get("authors", [])
        ]
        new_papers.append({
            "source": "IEEE Xplore",
            "title": title,
            "year": article.get("publication_year"),
            "authors": authors,
            "doi": doi,
            "bibtex": None,
            "ieeexplore": article.get("html_url") or article.get("pdf_url"),
            "semanticscholar": None,
            "arxiv": None,
            "url": None,
        })
    print(f"  -> {len(new_papers)} new results")
    return new_papers


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Search for new dVRK papers and add them interactively to publications.bib",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--start-year", type=int, default=2021, help="Start year (default: 2021)")
    parser.add_argument("--end-year",   type=int, default=2025, help="End year   (default: 2025)")
    parser.add_argument("--bib",        default="publications.bib", help="Path to bib file")
    args = parser.parse_args()

    existing_dois, existing_titles = load_existing_data(args.bib)
    rejected_dois = load_rejected_dois(REJECTED_FILE)
    print(f"Loaded {len(existing_dois)} existing DOIs, {len(existing_titles)} existing titles, "
          f"{len(rejected_dois)} rejected items.\n")

    queries = ["dVRK", "da Vinci Research Kit"]
    years   = list(range(args.start_year, args.end_year + 1))

    all_new: list[dict] = []
    seen_titles: set[str] = set()

    def add_results(papers):
        for p in papers:
            t = (p.get("title") or "").lower()
            if t and t not in seen_titles and t not in existing_titles:
                all_new.append(p)
                seen_titles.add(t)

    # --- CrossRef (primary, no key needed) ---
    for q in queries:
        add_results(search_crossref(q, args.start_year, args.end_year,
                                    existing_dois, existing_titles, rejected_dois))
        time.sleep(1)   # polite

    # --- arXiv (good for preprints, no key needed) ---
    for q in queries:
        add_results(search_arxiv(q, args.start_year, args.end_year,
                                 existing_dois, existing_titles, rejected_dois))
        time.sleep(1)

    # --- Semantic Scholar (optional, rate-limited without key) ---
    for q in queries:
        add_results(search_semantic_scholar(q, years,
                                            existing_dois, existing_titles, rejected_dois))
        time.sleep(2)

    # --- IEEE Xplore (optional, requires key) ---
    for q in queries:
        add_results(search_ieee_xplore(q, args.start_year, args.end_year,
                                       existing_dois, existing_titles, rejected_dois))
        time.sleep(1)

    if not all_new:
        print("\nNo new papers found.")
        return

    print(f"\nFound {len(all_new)} potential new papers.\n")

    # --- Interactive review ---
    for i, paper in enumerate(all_new, 1):
        print("\n" + "=" * 70)
        print(f"  Paper {i}/{len(all_new)}  [{paper['source']}]")
        print(f"  Title:   {paper['title']}")
        authors = paper.get("authors") or []
        print(f"  Authors: {', '.join(authors[:4])}{' et al.' if len(authors) > 4 else ''}")
        print(f"  Year:    {paper.get('year')}")
        if paper.get("venue"):
            print(f"  Venue:   {paper['venue']}")

        # Try to get high-quality BibTeX via doi.org
        bibtex_val = paper.get("bibtex") or ""
        if paper.get("doi") and not bibtex_val.startswith("@article") \
                and not bibtex_val.startswith("@inproceedings"):
            print("  Fetching BibTeX from doi.org...", end=" ", flush=True)
            bib = doi_to_bibtex(paper["doi"])
            if bib:
                paper["bibtex"] = bib
                print("✓")
            else:
                print("failed, will use fallback.")

        if paper.get("bibtex"):
            print("\n  --- BibTeX preview ---")
            preview = paper["bibtex"]
            print(preview[:500] + ("..." if len(preview) > 500 else ""))
            print("  ----------------------")
        else:
            print("  ⚠️  No BibTeX available — entry will NOT be well-formed if added.")

        # Links
        for label, key in [("DOI", "doi"), ("arXiv", "arxiv"), ("IEEE", "ieeexplore"),
                            ("S2", "semanticscholar"), ("URL", "url")]:
            if paper.get(key):
                print(f"  {label}: {paper[key]}")

        # Open in browser
        open_url = (
            (f"https://doi.org/{paper['doi']}" if paper.get("doi") else None)
            or paper.get("arxiv")
            or paper.get("ieeexplore")
            or paper.get("semanticscholar")
            or paper.get("url")
        )
        if open_url:
            webbrowser.open(open_url)

        # Prompt
        while True:
            choice = input("\n  Add? [y]es / [n]o (reject) / [s]kip / [q]uit: ").lower().strip()
            if choice in ("y", "yes"):
                if append_to_bib(paper, args.bib):
                    existing_titles.add(paper["title"].lower())
                    if paper.get("doi"):
                        existing_dois.add(paper["doi"].lower())
                break
            elif choice in ("n", "no"):
                save_rejected(paper, REJECTED_FILE)
                print("  ❌ Rejected.")
                break
            elif choice in ("s", "skip"):
                print("  ⏭  Skipped.")
                break
            elif choice in ("q", "quit"):
                print("Exiting.")
                sys.exit(0)
            else:
                print("  Please type y, n, s, or q.")

    print("\n" + "=" * 70)
    print("Review complete. Run 'python3 scripts/cleanup_bib.py' to normalise the bib file.")


if __name__ == "__main__":
    main()
