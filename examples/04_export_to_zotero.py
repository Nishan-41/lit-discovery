"""Example 4: 1-Click Reference Export to Zotero, Overleaf (BibTeX), and Mendeley (RIS)."""
import os
from lit_discovery import search_literature, export_zotero_references

def main():
    query = "polybenzoxazole rigid-rod electrolyte"
    print(f"[*] Searching literature for: '{query}'...")

    res = search_literature(query_text=query, limit_per_engine=2, top_n=4)
    articles = res["articles"]

    bib_path = "exported_references.bib"
    ris_path = "exported_references.ris"

    print(f"[*] Exporting citations to '{bib_path}' and '{ris_path}'...")
    stats = export_zotero_references(articles, bib_path=bib_path, ris_path=ris_path)

    print(f"[+] Export summary:")
    print(f"    • BibTeX entries written: {stats['bibtex_count']} -> {os.path.abspath(bib_path)}")
    print(f"    • RIS entries written: {stats['ris_count']} -> {os.path.abspath(ris_path)}")

    if os.path.exists(bib_path):
        print("\n--- BibTeX Preview ---")
        with open(bib_path, "r", encoding="utf-8") as f:
            print(f.read()[:500] + "...\n")

if __name__ == "__main__":
    main()
