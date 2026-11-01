"""Example 3: OpenAlex citation network traversal."""
from lit_discovery import explore_citation_graph

def main():
    seed_doi = "10.1039/c9ta01153a"
    print(f"[*] Exploring citation graph around seed: {seed_doi}...")

    # Provider-supplied related works
    graph = explore_citation_graph(seed_doi, mode="related", limit=5)

    if graph.get("status") != "success":
        print(f"[-] Error: {graph.get('error')}")
        return

    seed = graph.get("seed_paper", {})
    print(f"\n[+] Seed Work: {seed.get('title')} ({seed.get('year')})")
    print(f"[+] Discovered {graph.get('total_connected')} related works:\n")

    for i, w in enumerate(graph.get("connected_works", []), 1):
        sc = w.get("smart_citations") or {}
        sc_str = f"🟢 {sc.get('supporting', 0)} Supp / 🔴 {sc.get('contrasting', 0)} Cont" if sc.get("total_citations", 0) > 0 else "Neutral"
        print(f"{i}. {w.get('title')} ({w.get('year')})")
        print(f"   Authors: {', '.join(w.get('authors', [])[:3])}")
        print(f"   DOI: {w.get('doi')} | scite.ai: {sc_str}")
        if w.get("open_access_pdf"):
            print(f"   Direct OA PDF: {w.get('open_access_pdf')}")
        print()

if __name__ == "__main__":
    main()
