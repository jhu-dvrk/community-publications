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

# Mutable container for delay state
# [current_delay]
delay_state = [1.5]

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
                # "if 5s works, return to 1.5"
                delay_state[0] = 1.5
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

def get_semantic_scholar_data(title, doi=None, progress_prefix=""):
    base_url = "https://api.semanticscholar.org/graph/v1/paper"
    
    # Try searching by DOI first if available
    if doi:
        url = f"{base_url}/DOI:{doi}"
        params = {"fields": "url,externalIds,title,abstract,openAccessPdf"}
        data = fetch_with_adaptive_delay(url, params, progress_prefix)
        if data:
            return data

    # Fallback to search by title
    if title:
        search_url = f"{base_url}/search"
        params = {
            "query": title,
            "fields": "url,externalIds,title,year,abstract,openAccessPdf",
            "limit": 1
        }
        data = fetch_with_adaptive_delay(search_url, params, progress_prefix)
        if data and data.get("data"):
            return data["data"][0]
            
    return None

def enrich_bib(file_path):
    print(f"Enriching {file_path} with Semantic Scholar data...")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    entries = re.split(r'(?m)^@', content)
    enriched_entries = []
    updated_count = 0
    
    total_entries = len([e for e in entries if e.strip()])
    current_idx = 0

    for raw in entries:
        if not raw.strip():
            continue
            
        current_idx += 1
        # Print progress, overwriting weight message
        progress_msg = f"Processing {current_idx}/{total_entries}..."
        sys.stdout.write(f"\r{progress_msg}{' '*20}")
        sys.stdout.flush()
        
        full_entry = "@" + raw
        
        # Extract fields
        title_match = re.search(r'title\s*=\s*[{"\'](.+?)[}"\'],?\s*\n', raw, re.IGNORECASE | re.DOTALL)
        if not title_match:
             title_match = re.search(r'title\s*=\s*[{"\'](.+?)[}"\']', raw, re.IGNORECASE)
        title = title_match.group(1) if title_match else ""
        title = re.sub(r'\s+', ' ', title).strip().strip('{}').strip('""')
        
        doi_match = re.search(r'doi\s*=\s*[{"\'](.+?)[}"\']', raw, re.IGNORECASE)
        doi = doi_match.group(1) if doi_match else None
        
        sem_match = re.search(r'semanticscholar\s*=\s*', raw, re.IGNORECASE)
        url_match = re.search(r'url\s*=\s*', raw, re.IGNORECASE)
        
        abstract_match = re.search(r'abstract\s*=\s*', raw, re.IGNORECASE)
        
        needs_sem = sem_match is None
        needs_doi = doi is None
        needs_abs = abstract_match is None
        needs_url = url_match is None
        
        changes = []
        
        if (needs_sem or needs_doi or needs_abs or (needs_url and not doi)) and title:
            # Fetch data (Adaptive delay handled inside)
            data = get_semantic_scholar_data(title, doi, progress_msg + " ")
            
            if data:
                if needs_sem and data.get("url"):
                    sem_url = data.get("url")
                    changes.append(f"  semanticscholar = {{{sem_url}}}")
                    
                if needs_doi and data.get("externalIds") and data["externalIds"].get("DOI"):
                    new_doi = data["externalIds"]["DOI"]
                    changes.append(f"  doi = {{{new_doi}}}")
                    
                if needs_abs and data.get("abstract"):
                    abstract = data["abstract"].replace("{", "\\{").replace("}", "\\}")
                    changes.append(f"  abstract = {{{abstract}}}")
                    
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
        
        # NOTE: Explicit time.sleep(1.5) loop removed here.
        # It is now handled inside fetch_with_adaptive_delay before each request.

    print(f"\nUpdated {updated_count} entries.")
    
    shutil.copy(file_path, file_path + ".enriched.bak")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        for entry in enriched_entries:
            f.write(entry.strip())
            f.write("\n\n")

if __name__ == "__main__":
    file_path = "publications.bib"
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    enrich_bib(file_path)
