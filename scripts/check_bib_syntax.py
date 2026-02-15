import re

def check_bib(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split by entries
    entries = re.split(r'(?m)^@', content)
    for i, raw in enumerate(entries):
        if not raw.strip():
            continue
            
        full_entry = "@" + raw
        
        # Count braces
        opened = full_entry.count('{')
        closed = full_entry.count('}')
        
        if opened != closed:
            # Find the header to identify the entry
            header_match = re.match(r'@\w+\{(.+?),', full_entry)
            key = header_match.group(1) if header_match else "unknown"
            print(f"FAILED: Entry '{key}' has unbalanced braces: {opened} opened, {closed} closed")
            
        # Check for multiple equals signs on one line (possible line merge corruption)
        # or other suspicious patterns.
        
    print("Done checking.")

if __name__ == "__main__":
    check_bib('publications.bib')
