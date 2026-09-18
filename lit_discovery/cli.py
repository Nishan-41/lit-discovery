"""Command-line interface (CLI) for LitDiscovery."""
import argparse
import json
import sys

from lit_discovery import (
    search_literature,
    explore_citation_graph,
    deep_read_pdf,
    export_zotero_references,
    __version__
)


if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def print_banner():
    banner = r"""
  _      _ _     _____  _                                  
 | |    (_) |   |  __ \(_)                                 
 | |     _| |_  | |  | |_ ___  ___ _____   _____ _ __ _   _ 
 | |    | | __| | |  | | / __|/ __/ _ \ \ / / _ \ '__| | | |
 | |____| | |_  | |__| | \__ \ (_| (_) \ V /  __/ |  | |_| |
 |______|_|\__| |_____/|_|___/\___\___/ \_/ \___|_|   \__, |
                                                       __/ |
       Scientific Literature Discovery & Consensus    |___/ 
    """
    print(banner)


def cmd_search(args):
    engines = [e.strip() for e in args.engines.split(",")] if args.engines else None
    print(f"[*] Querying literature engines for: '{args.query}'...")
    data = search_literature(
        query_text=args.query,
        selected_engines=engines,
        limit_per_engine=args.limit,
        top_n=args.top,
        enrich=not args.no_enrich
    )

    if args.json:
        print(json.dumps(data, indent=2))
        return

    print(f"\n[+] Successfully retrieved {data.get('total_articles_retrieved', 0)} papers across {len(data.get('engines_queried', []))} engines.")
    print(f"[+] Showing top {len(data.get('articles', []))} enriched articles sorted by relevance:\n")

    for idx, art in enumerate(data.get("articles", []), 1):
        sc = art.get("smart_citations") or {}
        sc_str = f"🟢 {sc.get('supporting', 0)} Supp | 🔴 {sc.get('contrasting', 0)} Cont" if sc.get("total_citations", 0) > 0 else "Neutral / 0"
        oa_str = f"OA PDF: {art.get('open_access_pdf')}" if art.get("open_access_pdf") else "OA PDF: None"
        score = art.get("relevance", {}).get("score_percent", 0)

        print(f"{idx}. {art.get('title')}")
        print(f"   Authors: {', '.join(art.get('authors', [])[:3])} ({art.get('year')}) | {art.get('journal', 'Journal')}")
        print(f"   DOI: {art.get('doi')} | Match: {score}%")
        print(f"   scite.ai: {sc_str} | {oa_str}")
        print(f"   Abstract: {art.get('abstract', '')[:160]}...\n")

    if data.get("synthesis_table_markdown"):
        print("=" * 80)
        print("COMPARATIVE SYNTHESIS MATRIX")
        print("=" * 80)
        print(data["synthesis_table_markdown"])

    if args.bib or args.ris:
        print(f"\n[*] Exporting citations to Zotero/Mendeley formats...")
        export_zotero_references(data.get("articles", []), bib_path=args.bib, ris_path=args.ris)
        if args.bib:
            print(f"[+] BibTeX saved to: {args.bib}")
        if args.ris:
            print(f"[+] RIS saved to: {args.ris}")


def cmd_graph(args):
    print(f"[*] Exploring citation graph for seed: '{args.seed}' (Mode: {args.mode})...")
    data = explore_citation_graph(seed_doi_or_query=args.seed, mode=args.mode, limit=args.limit)

    if args.json:
        print(json.dumps(data, indent=2))
        return

    if data.get("status") != "success":
        print(f"[-] Graph exploration failed: {data.get('error') or data.get('message')}")
        return

    seed = data.get("seed_paper") or data.get("seed_work") or {}
    print(f"\n[+] Seed Work: {seed.get('title')} ({seed.get('year')})")
    print(f"    DOI: {seed.get('doi')}")
    print(f"\n[+] Discovered {len(data.get('connected_works', []))} connected works ({data.get('mode')}):\n")

    for idx, w in enumerate(data.get("connected_works", []), 1):
        sc = w.get("smart_citations") or {}
        sc_str = f"🟢 {sc.get('supporting', 0)} Supp | 🔴 {sc.get('contrasting', 0)} Cont" if sc.get("total_citations", 0) > 0 else "Neutral / 0"
        print(f"{idx}. {w.get('title')} ({w.get('year')})")
        print(f"   DOI: {w.get('doi')} | scite.ai: {sc_str}")
        if w.get("open_access_pdf"):
            print(f"   PDF: {w.get('open_access_pdf')}")
        print()


def cmd_read(args):
    print(f"[*] Streaming PDF into memory: '{args.target}'...")
    data = deep_read_pdf(target_doi_or_url=args.target, max_pages=args.pages)

    if args.json:
        print(json.dumps(data, indent=2))
        return

    if data.get("status") != "success":
        print(f"[-] Deep read failed: {data.get('error') or data.get('message')}")
        return

    print(f"\n[+] Successfully parsed {data.get('pages_analyzed')}/{data.get('total_pages')} pages ({data.get('character_count'):,} characters).")
    print(f"    Source: {data.get('pdf_url')}\n")

    props = data.get("extracted_properties", {})
    print("=" * 60)
    print("EXTRACTED EXPERIMENTAL PARAMETERS")
    print("=" * 60)
    for k, v in props.items():
        print(f"• {k.replace('_', ' ').title()}: {', '.join(v) if isinstance(v, list) else v}")

    sections = data.get("sections", {})
    if sections.get("experimental_methods"):
        print("\n" + "=" * 60)
        print("EXPERIMENTAL METHODS PREVIEW")
        print("=" * 60)
        print(sections["experimental_methods"][:800] + "...\n")


def cmd_ui(args):
    from lit_discovery.web_app import run_server
    run_server(host=args.host, port=args.port)


def main():
    parser = argparse.ArgumentParser(
        prog="lit-discovery",
        description="LitDiscovery: Open-Source Scientific Literature Discovery, Smart Citation Consensus, and Research Intelligence."
    )
    parser.add_argument("-v", "--version", action="version", version=f"lit-discovery {__version__}")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Search
    p_search = subparsers.add_parser("search", help="Search scientific literature across 12 academic engines")
    p_search.add_argument("query", help="Scientific query string")
    p_search.add_argument("--engines", help="Comma-separated engine names (e.g. 'openalex,arxiv,crossref')")
    p_search.add_argument("--limit", type=int, default=5, help="Results per engine (default: 5)")
    p_search.add_argument("--top", type=int, default=10, help="Top enriched articles (default: 10)")
    p_search.add_argument("--no-enrich", action="store_true", help="Skip Unpaywall and scite.ai enrichment")
    p_search.add_argument("--bib", help="Path to save BibTeX (.bib) file")
    p_search.add_argument("--ris", help="Path to save RIS (.ris) file")
    p_search.add_argument("--json", action="store_true", help="Output full response as JSON")

    # Graph
    p_graph = subparsers.add_parser("graph", help="Explore citation networks (Connected Papers style)")
    p_graph.add_argument("seed", help="Seed DOI or title")
    p_graph.add_argument("--mode", choices=["related", "forward", "backward"], default="related", help="Graph mode")
    p_graph.add_argument("--limit", type=int, default=6, help="Max connected works")
    p_graph.add_argument("--json", action="store_true", help="Output as JSON")

    # Read
    p_read = subparsers.add_parser("read", help="PyMuPDF in-memory deep reader for experimental extraction")
    p_read.add_argument("target", help="Target DOI or direct open-access PDF URL")
    p_read.add_argument("--pages", type=int, default=30, help="Max pages to inspect (default: 30)")
    p_read.add_argument("--json", action="store_true", help="Output as JSON")

    # UI
    p_ui = subparsers.add_parser("ui", help="Launch interactive browser Web UI")
    p_ui.add_argument("--host", default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    p_ui.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")

    args = parser.parse_args()

    if not args.command:
        print_banner()
        parser.print_help()
        sys.exit(0)

    if args.command == "search":
        cmd_search(args)
    elif args.command == "graph":
        cmd_graph(args)
    elif args.command == "read":
        cmd_read(args)
    elif args.command == "ui":
        cmd_ui(args)


if __name__ == "__main__":
    main()
