"""Example 1: Basic Literature Search & Comparative Matrix Generation."""
from lit_discovery import search_literature

def main():
    query = "polybenzoxazole ionogel mechanical properties ionic conductivity"
    print(f"[*] Searching literature for: '{query}'...")

    # Run search across 12 academic engines with automated synthesis
    results = search_literature(query_text=query, limit_per_engine=3, top_n=5)

    print(f"\n[+] Total papers retrieved across engines: {results['total_articles_retrieved']}")
    print(f"[+] Top {len(results['articles'])} papers displayed:\n")

    for idx, paper in enumerate(results["articles"], 1):
        print(f"{idx}. {paper['title']}")
        print(f"   Authors: {', '.join(paper['authors'][:3])} ({paper['year']})")
        print(f"   DOI: {paper['doi']}")
        print(f"   Relevance: {paper['relevance']['score_percent']}% ({paper['relevance']['confidence_tier']})")
        if paper.get("open_access_pdf"):
            print(f"   Direct OA PDF: {paper['open_access_pdf']}")
        print()

    print("=" * 80)
    print("METADATA SYNTHESIS (UNVERIFIED CANDIDATES)")
    print("=" * 80)
    print(results["synthesis_table_markdown"])

if __name__ == "__main__":
    main()
