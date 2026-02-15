#!/usr/bin/env python3
import requests
import json
import time
import sys
import os
import webbrowser

# --- Configuration ---
# You can set your IEEE API key here or via an environment variable
IEEE_API_KEY = os.environ.get("IEEE_API_KEY", "") 

REJECTED_FILE = "rejected_papers.json"

def load_rejected_dois(rejected_path):
    dois = set()
    if os.path.exists(rejected_path):
        try:
            with open(rejected_path, "r") as f:
                rejected_list = json.load(f)
                for item in rejected_list:
                    if "doi" in item and item["doi"]:
                        dois.add(item["doi"].lower())
                    if "title" in item and item["title"]:
                        dois.add(item["title"].lower()) # Also track titles if DOI missing
        except Exception as e:
            print(f"Error reading rejected file: {e}")
    return dois

def save_rejected(paper, rejected_path):
    rejected_list = []
    if os.path.exists(rejected_path):
        try:
            with open(rejected_path, "r") as f:
                rejected_list = json.load(f)
        except:
            pass
    
    # Check if already in list to avoid duplicates
    if paper not in rejected_list:
        rejected_list.append(paper)
        
    with open(rejected_path, "w") as f:
        json.dump(rejected_list, f, indent=2)

def append_to_bib(paper, bib_path):
    if not paper.get("bibtex"):
        print("Cannot add: No BibTeX available.")
        return False
        
    try:
        with open(bib_path, "a") as f:
            f.write("\n")
            f.write(paper["bibtex"])
            f.write("\n")
        print(f"Added {paper['title']} to {bib_path}")
        return True
    except Exception as e:
        print(f"Error appending to bib file: {e}")
        return False

def load_existing_data(bib_path):
    dois = set()
    titles = set()
    try:
        with open(bib_path, "r") as f:
            for line in f:
                line = line.strip()
                if line.lower().startswith("doi =") or line.lower().startswith("doi="):
                     parts = line.split("=", 1)
                     if len(parts) > 1:
                         doi = parts[1].strip().strip(",").strip('"').strip("{").strip("}")
                         dois.add(doi.lower())
                elif line.lower().startswith("title =") or line.lower().startswith("title="):
                     parts = line.split("=", 1)
                     if len(parts) > 1:
                         title = parts[1].strip().strip(",").strip('"').strip("{").strip("}")
                         titles.add(title.lower())
    except Exception as e:
        print(f"Error reading bib file: {e}")
    return dois, titles

def fetch_with_retry(url, params, retries=3, delay=5):
    for i in range(retries):
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                print(f"Rate limited. Waiting {delay} seconds (Attempt {i+1}/{retries})...")
                time.sleep(delay)
                delay *= 2
            else:
                print(f"Error {response.status_code}: {response.text}")
                # Don't break immediately for 5xx errors, retry
                if 500 <= response.status_code < 600:
                    time.sleep(delay)
                else:
                    break
        except Exception as e:
            print(f"Request exception: {e}")
            time.sleep(delay)
    return None

def search_semantic_scholar(query, years, existing_dois, existing_titles, rejected_dois):
    search_url = "https://api.semanticscholar.org/graph/v1/paper/search"
    # Search for year range
    year_range = f"{years[0]}-{years[-1]}"
    print(f"Searching Semantic Scholar for '{query}' in {year_range}...")
    
    params = {
        "query": query,
        "year": year_range,
        "fields": "title,authors,year,journal,venue,publicationVenue,externalIds,citationStyles,url",
        "limit": 100 
    }
    
    data = fetch_with_retry(search_url, params)
    
    new_papers = []
    if data and data.get("data"):
        for paper in data["data"]:
            doi = paper.get("externalIds", {}).get("DOI")
            title = paper.get("title")
            
            # Skip if already in bib file
            if doi and doi.lower() in existing_dois:
                continue
            if title and title.lower() in existing_titles:
                continue

            # Skip if rejected
            if doi and doi.lower() in rejected_dois:
                continue
            if title and title.lower() in rejected_dois: # Title check
                continue
            
            new_papers.append({
                "source": "Semantic Scholar",
                "title": title,
                "year": paper.get("year"),
                "authors": [a.get("name") for a in paper.get("authors", [])],
                "bibtex": paper.get("citationStyles", {}).get("bibtex"),
                "doi": doi,
                "url": paper.get("url")
            })
    return new_papers

def search_ieee_xplore(query, start_year, end_year, existing_dois, existing_titles, rejected_dois):
    if not IEEE_API_KEY:
        print("Skipping IEEE Xplore search: No API Key provided.")
        return []
        
    search_url = "http://ieeexploreapi.ieee.org/api/v1/search/articles"
    print(f"Searching IEEE Xplore for '{query}' from {start_year} to {end_year}...")
    
    params = {
        "apikey": IEEE_API_KEY,
        "format": "json",
        "max_records": 100,
        "start_year": start_year,
        "end_year": end_year,
        "querytext": query
    }
    
    data = fetch_with_retry(search_url, params)
    
    new_papers = []
    if data and data.get("articles"):
         for article in data["articles"]:
            doi = article.get("doi")
            title = article.get("title")
            
            if doi and doi.lower() in existing_dois:
                continue
            if title and title.lower() in existing_titles:
                continue
                
            if doi and doi.lower() in rejected_dois:
                continue
            if title and title.lower() in rejected_dois:
                continue

            authors = []
            if "authors" in article and "authors" in article["authors"]:
                 for a in article["authors"]["authors"]:
                     authors.append(a.get("full_name", ""))
            
            new_papers.append({
                "source": "IEEE Xplore",
                "title": title,
                "year": article.get("publication_year"),
                "authors": authors,
                "bibtex": None, # Needs separate fetch or construction
                "doi": doi,
                "url": article.get("pdf_url")
            })
            
    return new_papers

if __name__ == "__main__":
    bib_path = "publications.bib"
    existing_dois, existing_titles = load_existing_data(bib_path)
    rejected_dois = load_rejected_dois(REJECTED_FILE)
    print(f"Loaded {len(existing_dois)} existing DOIs, {len(existing_titles)} existing titles, and {len(rejected_dois)} rejected items.")
    
    years = list(range(2021, 2026)) # 2021 to 2025
    queries = ["dVRK", "da Vinci Research Kit"]
    
    all_new_papers = []
    seen_titles = set()
    
    # 1. Semantic Scholar Search
    for q in queries:
        found = search_semantic_scholar(q, years, existing_dois, existing_titles, rejected_dois)
        for p in found:
            t = p["title"].lower() if p["title"] else ""
            if t and t not in seen_titles:
                all_new_papers.append(p)
                seen_titles.add(t)
        time.sleep(2) # Be nice
        
    # 2. IEEE Xplore Search
    # Note: This will only run if IEEE_API_KEY is set
    for q in queries:
        found = search_ieee_xplore(q, 2021, 2025, existing_dois, existing_titles, rejected_dois)
        for p in found:
            t = p["title"].lower() if p["title"] else ""
            if t and t not in seen_titles:
                all_new_papers.append(p)
                seen_titles.add(t)
        time.sleep(2)

    # Output results and Interactive Review
    if not all_new_papers:
        print("No new papers found.")
    else:
        print(f"Found {len(all_new_papers)} potential new papers.")
        
        # Interact with the user
        print(f"Starting interactive review...")
        for i, paper in enumerate(all_new_papers):
            print("\n" + "=" * 60)
            print(f"Paper {i+1}/{len(all_new_papers)}")
            print(f"Title: {paper['title']}")
            print(f"Authors: {', '.join(paper['authors'][:3])}{' et al.' if len(paper['authors']) > 3 else ''}")
            print(f"Year: {paper['year']}")
            print(f"Source: {paper['source']}")
            print(f"URL: {paper['url'] or 'N/A'}")
            
            if paper.get('url'):
                print("Opening in browser...")
                webbrowser.open(paper['url'])
            
            if not paper['bibtex']:
                print("Warning: BibTeX NOT available.")
            
            while True:
                choice = input("Add this paper? ([y]es/[n]o/[s]kip/[q]uit): ").lower().strip()
                if choice in ['y', 'yes']:
                    if append_to_bib(paper, bib_path):
                         existing_dois.add(paper['doi']) if paper['doi'] else None
                         break
                    else:
                        print("Failed to add.")
                        break
                elif choice in ['n', 'no']:
                    save_rejected({"doi": paper['doi'], "title": paper['title']}, REJECTED_FILE)
                    print("Paper rejected.")
                    break
                elif choice in ['s', 'skip']:
                    print("Skipped.")
                    break
                elif choice in ['q', 'quit']:
                    print("Exiting review.")
                    sys.exit(0)
                else:
                    print("Invalid choice.")
