#!/usr/bin/env python3
"""
Script to enrich BibTeX metadata using Semantic Scholar API.
Implements adaptive rate limiting.
"""
import re
import time
import json
import requests
import shutil
import sys
import argparse
import hashlib
import os
import difflib

# Mutable container for delay state
# [current_delay]
delay_state = [3.0]

CACHE_DIR = "cache"

def get_cache_path(identifier):
    """Generate a stable filename for a given identifier."""
    # Use MD5 for a reasonably short but unique filename
    hash_obj = hashlib.md5(identifier.encode('utf-8'))
    return os.path.join(CACHE_DIR, f"{hash_obj.hexdigest()}.json")

def is_cache_valid(cache_path, max_days):
    """Check if cache file exists and is within the expiration period."""
    if max_days == 0:
        return False
    if not os.path.exists(cache_path):
        return False
    
    file_mtime = os.path.getmtime(cache_path)
    current_time = time.time()
    age_days = (current_time - file_mtime) / (24 * 3600)
    
    return age_days <= max_days

def load_cache(cache_path):
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading cache {cache_path}: {e}")
        return None

def save_cache(cache_path, data):
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error writing cache {cache_path}: {e}")

def fetch_with_adaptive_delay(url, params, progress_prefix=""):
    # Retry loop implementing 1.5 -> 3 -> 5 logic
    # We loop as long as we get 429s, up to the max delay state (5s)
    # Actually, we can loop indefinitely or cap attempts?
    # User said: "start at 1.5s, then 3s and thereafter 5s"
    # This implies if 5s fails, we keep trying at 5s? Or fail?
    # Let's assume we retry a few times at 5s then give up, or just keep trying 5s (safe).
    # But to avoid infinite loops, let's limit total attempts.
    
    max_attempts = 5 
    
    for attempt in range(max_attempts):
        current_delay = delay_state[0]
        
        # Sleep *before* request to enforce rate limit
        # This replaces the loop sleep
        sys.stdout.write(f"\r{progress_prefix}Waiting {current_delay}s...{' '*10}")
        sys.stdout.flush()
        time.sleep(current_delay)
        
        try:
            response = requests.get(url, params=params)
            
            if response.status_code == 200:
                # Success!
                # "if 5s works, return to 2.0"
                delay_state[0] = 2.0
                return response.json()
                
            elif response.status_code == 429:
                # Rate limited
                print(f"\rRate limited (429).")
                # Increase delay: 1.5 -> 3 -> 5
                if delay_state[0] < 3:
                    delay_state[0] = 3.0
                elif delay_state[0] < 5:
                    delay_state[0] = 5.0
                # If already 5, stays 5.
                
                # Continue loop to retry with new delay
                continue
                
            elif response.status_code == 404:
                return None
                
            else:
                print(f"\rError {response.status_code}: {response.text}")
                # Non-recoverable error?
                return None
                
        except Exception as e:
            print(f"\rRequest exception: {e}")
            time.sleep(current_delay) 
            
    return None

MASTHEAD_RE = re.compile(
    r"(is published by the ieee|joint publication of the ieee|for membership and subscription|"
    r"international conference on intelligent robots and systems.*(?:will be held|was held)|"
    r"innovative preprint repository,\s*arxiv,\s*was created|"
    r"guest editors\s*:.*professor of)",
    re.IGNORECASE | re.DOTALL,
)

def normalize_compare_text(s):
    if not s:
        return ""
    s = re.sub(r"[{}]", "", s)
    s = re.sub(r"[^a-zA-Z0-9]+", " ", s.lower())
    return " ".join(s.split())

def extract_author_surnames(author_str):
    surnames = set()
    if not author_str:
        return surnames
    for raw in re.split(r"\s+and\s+", author_str, flags=re.IGNORECASE):
        raw = re.sub(r"[{}]", "", raw).strip()
        if not raw:
            continue
        last = raw.split(",")[0].strip() if "," in raw else (raw.split()[-1] if raw.split() else "")
        for tok in normalize_compare_text(last).split():
            if len(tok) >= 2:
                surnames.add(tok)
    return surnames

def extract_bib_field(raw_entry, field_name):
    """Extract a BibTeX field value handling nested curly braces and apostrophes safely."""
    pattern = re.compile(r"(?im)^\s*" + re.escape(field_name) + r"\s*=\s*")
    m = pattern.search(raw_entry)
    if not m:
        return None
    pos = m.end()
    if pos >= len(raw_entry):
        return None
    opener = raw_entry[pos]
    if opener == "{":
        depth = 1
        pos += 1
        start = pos
        while pos < len(raw_entry) and depth > 0:
            ch = raw_entry[pos]
            if ch == "\\" and pos + 1 < len(raw_entry):
                pos += 2
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            pos += 1
        return raw_entry[start:pos - 1].strip() if depth == 0 else None
    elif opener == '"':
        depth = 0
        pos += 1
        start = pos
        while pos < len(raw_entry):
            ch = raw_entry[pos]
            if ch == "\\" and pos + 1 < len(raw_entry):
                pos += 2
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth = max(0, depth - 1)
            elif ch == '"' and depth == 0:
                return raw_entry[start:pos].strip()
            pos += 1
        return None
    else:
        end_m = re.search(r"[,\r\n}]", raw_entry[pos:])
        return raw_entry[pos:pos + end_m.start()].strip() if end_m else raw_entry[pos:].strip()

def is_valid_match(title, result, bib_authors=""):
    """Check if a Semantic Scholar result is a genuine match for the given title and authors."""
    norm_title = normalize_compare_text(title)
    norm_res = normalize_compare_text(result.get("title") or "")
    if not norm_title or not norm_res:
        return False, 0.0

    # Guard against truncated or 1-word query collisions
    similarity = difflib.SequenceMatcher(None, norm_title, norm_res).ratio()

    # Check for generic proceedings/journal records
    publication_types = result.get("publicationTypes") or []
    is_generic = any(t in ["Conference", "Journal"] for t in publication_types)

    score = similarity
    if is_generic:
        score -= 0.3  # Penalize generic entries

    # Require author surname overlap when both sides list authors
    bib_surnames = extract_author_surnames(bib_authors)
    res_authors = result.get("authors") or []
    if bib_surnames and res_authors:
        res_surnames = set()
        for a in res_authors:
            name = normalize_compare_text((a or {}).get("name") or "")
            for tok in name.split():
                if len(tok) >= 2:
                    res_surnames.add(tok)
        if res_surnames and not (bib_surnames & res_surnames) and similarity < 0.96:
            return False, 0.0

    return score > 0.78, score

def get_semantic_scholar_data(title, doi=None, progress_prefix="", max_cache_days=180, reprocess=False, bib_authors=""):
    base_url = "https://api.semanticscholar.org/graph/v1/paper"
    
    # Try searching by DOI first if available
    if doi:
        cache_path = get_cache_path(f"doi:{doi}")
        if os.path.exists(cache_path):
            data = load_cache(cache_path)
            if data:
                is_valid, _ = is_valid_match(title, data, bib_authors)
                if is_valid and (is_cache_valid(cache_path, max_cache_days) or reprocess):
                    return data
                elif reprocess and not is_valid:
                    return None

        if not reprocess:
            url = f"{base_url}/DOI:{doi}"
            params = {"fields": "url,externalIds,title,abstract,openAccessPdf,publicationTypes,authors"}
            data = fetch_with_adaptive_delay(url, params, progress_prefix)
            if data:
                save_cache(cache_path, data)
                is_valid, _ = is_valid_match(title, data, bib_authors)
                if is_valid:
                    return data

    # Fallback to search by title
    if title and len(normalize_compare_text(title)) >= 12:
        cache_path = get_cache_path(f"title:{title.lower()}")
        if os.path.exists(cache_path):
            data = load_cache(cache_path)
            if data:
                # Validate cached record
                is_valid, score = is_valid_match(title, data, bib_authors)
                if is_valid:
                    if is_cache_valid(cache_path, max_cache_days) or reprocess:
                        return data
                elif reprocess:
                    # During reprocess, explicitly return None if cache is invalid
                    return None

        if not reprocess:
            search_url = f"{base_url}/search"
            params = {
                "query": title,
                "fields": "url,externalIds,title,year,abstract,openAccessPdf,publicationTypes,authors",
                "limit": 5
            }
            data = fetch_with_adaptive_delay(search_url, params, progress_prefix)
            if data and data.get("data"):
                # Filter and pick the best match
                results = data["data"]
                best_match = None
                highest_score = 0
                
                for result in results:
                    is_valid, score = is_valid_match(title, result, bib_authors)
                    if is_valid and score > highest_score:
                        highest_score = score
                        best_match = result
                
                # Threshold for accepting a match
                if best_match and highest_score > 0.78:
                    save_cache(cache_path, best_match)
                    return best_match
                else:
                    print(f"\rNo good match for '{title[:30]}...' (best score: {highest_score:.2f}){' '*20}")
            
    return None

def enrich_bib(file_path, max_cache_days=180, reprocess=False):
    print(f"Enriching {file_path} with Semantic Scholar data...")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    entries = re.split(r'(?m)^@', content)
    enriched_entries = []
    updated_count = 0
    
    total_entries = len([e for e in entries if e.strip()])
    current_idx = 0

    for idx, raw in enumerate(entries):
        if not raw.strip():
            # If it is the first entry and empty, we still want to keep it
            if idx == 0:
                enriched_entries.append("")
            continue
            
        current_idx += 1
        
        # Skip commented-out entries (like @comment)
        if raw.strip().lower().startswith("comment"):
            enriched_entries.append("@" + raw)
            continue
        # Print progress, overwriting weight message
        progress_msg = f"Processing {current_idx}/{total_entries}..."
        sys.stdout.write(f"\r{progress_msg}{' '*20}")
        sys.stdout.flush()
        
        full_entry = "@" + raw
        
        # Extract fields robustly using balanced-brace parser (handles nested {dVRK} and apostrophes)
        raw_title = extract_bib_field(raw, "title") or ""
        title = re.sub(r'[\{\}]', '', raw_title)
        title = re.sub(r'\s+', ' ', title).strip()

        raw_authors = extract_bib_field(raw, "author") or ""
        doi = extract_bib_field(raw, "doi")
        if doi:
            doi = doi.strip()
        
        sem_match = re.search(r'(?im)^\s*semanticscholar\s*=', raw)
        url_match = re.search(r'(?im)^\s*url\s*=', raw)
        abstract_match = re.search(r'(?im)^\s*abstract\s*=', raw)
        arxiv_match = re.search(r'(?im)^\s*arxiv\s*=', raw)
        
        needs_sem = sem_match is None
        needs_doi = doi is None
        needs_abs = abstract_match is None
        needs_url = url_match is None
        needs_arxiv = arxiv_match is None
        
        changes = []
        
        if (needs_sem or needs_doi or needs_abs or needs_arxiv or (needs_url and not doi)) and title:
            # Fetch data (Adaptive delay handled inside)
            data = get_semantic_scholar_data(title, doi, progress_msg + " ", max_cache_days, reprocess, bib_authors=raw_authors)
            
            if data:
                if needs_sem and data.get("url"):
                    sem_url = data.get("url")
                    changes.append(f"  semanticscholar = {{{sem_url}}}")
                    
                if needs_doi and data.get("externalIds") and data["externalIds"].get("DOI"):
                    new_doi = data["externalIds"]["DOI"]
                    changes.append(f"  doi = {{{new_doi}}}")
                    
                if needs_abs and data.get("abstract") and not MASTHEAD_RE.search(data["abstract"]):
                    abstract = data["abstract"].replace("{", "\\{").replace("}", "\\}")
                    changes.append(f"  abstract = {{{abstract}}}")

                if needs_arxiv and data.get("externalIds") and data["externalIds"].get("ArXiv"):
                    arxiv_id = data["externalIds"]["ArXiv"]
                    changes.append(f"  arxiv = {{https://arxiv.org/abs/{arxiv_id}}}")
                    
                # Only add url if doi is missing (either originally or just fetched)
                current_doi = doi or (data.get("externalIds") and data["externalIds"].get("DOI"))
                if needs_url and not current_doi and data.get("openAccessPdf") and data["openAccessPdf"].get("url"):
                    pdf_url = data["openAccessPdf"]["url"]
                    changes.append(f"  url = {{{pdf_url}}}")
        
        if changes:
             updated_count += 1
             # Find the last closing brace and ensure we insert correctly
             last_brace_idx = full_entry.rfind('}')
             if last_brace_idx != -1:
                 # Check if the preceding character (ignoring whitespace) is already a comma
                 prefix = full_entry[:last_brace_idx].rstrip()
                 insertion = ""
                 if not prefix.endswith(','):
                     insertion += ","
                 insertion += "\n" + ",\n".join(changes) + "\n"
                 full_entry = prefix + insertion + full_entry[last_brace_idx:]
                 
        enriched_entries.append(full_entry)
        
        # Save progress periodically
        if current_idx % 10 == 0:
            with open(file_path, 'w', encoding='utf-8') as f:
                for entry in enriched_entries:
                    f.write(entry.strip())
                    f.write("\n\n")
                # Append the rest of the original entries that haven't been processed yet
                for i in range(idx + 1, len(entries)):
                    e = entries[i]
                    if e.strip():
                        f.write("@" + e.strip())
                        f.write("\n\n")
        
        # NOTE: Explicit time.sleep(1.5) loop removed here.
        # It is now handled inside fetch_with_adaptive_delay before each request.

    print(f"\nUpdated {updated_count} entries.")
    
    shutil.copy(file_path, file_path + ".enriched.bak")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        for entry in enriched_entries:
            f.write(entry.strip())
            f.write("\n\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrich BibTeX metadata using Semantic Scholar API.")
    parser.add_argument("file", nargs="?", default="publications.bib", help="Path to the BibTeX file.")
    parser.add_argument("-d", "--days", type=int, default=180, help="Cache expiration in days. Use 0 to ignore cache. Default is 180.")
    parser.add_argument("-r", "--reprocess", action="store_true", help="Reprocess using only cached data. Skips network calls.")
    
    args = parser.parse_args()
    
    enrich_bib(args.file, args.days, args.reprocess)
