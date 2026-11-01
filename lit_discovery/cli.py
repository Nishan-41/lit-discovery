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
    print(f"LitDiscovery {__version__}")
    print("Scientific literature discovery from the terminal.\n")


def cmd_search(args):
    engines = [e.strip() for e in args.engines.split(",")] if args.engines else None
    print(f"[*] Querying literature engines for: '{args.query}'...", file=sys.stderr)
    data = search_literature(
        query_text=args.query,
        selected_engines=engines,
        limit_per_engine=args.limit,
        top_n=args.top,
        enrich=not args.no_enrich
    )

    if args.bib or args.ris:
        data["zotero_export"] = export_zotero_references(
            data.get("articles", []), bib_path=args.bib, ris_path=args.ris
        )
        print("[*] Citation exports complete.", file=sys.stderr)

    if args.json:
        print(json.dumps(data, indent=2))
        return

    print(f"\n[+] Successfully retrieved {data.get('total_articles_retrieved', 0)} papers across {len(data.get('engines_queried', []))} engines.")
    print(f"[+] Showing top {len(data.get('articles', []))} enriched articles sorted by relevance:\n")

    for idx, art in enumerate(data.get("articles", []), 1):
        sc = art.get("smart_citations") or {}
        sc_str = f"🟢 {sc.get('supporting', 0)} Supp | 🔴 {sc.get('contrasting', 0)} Cont" if sc.get("total_citations", 0) > 0 else "Unavailable or zero; inspect record"
        oa_str = f"OA PDF: {art.get('open_access_pdf')}" if art.get("open_access_pdf") else "OA PDF: None"
        score = art.get("relevance", {}).get("score_percent", 0)

        print(f"{idx}. {art.get('title')}")
        print(f"   Authors: {', '.join(art.get('authors', [])[:3])} ({art.get('year')}) | {art.get('journal', 'Journal')}")
        print(f"   DOI: {art.get('doi')} | Match: {score}%")
        print(f"   scite.ai: {sc_str} | {oa_str}")
        print(f"   Abstract: {(art.get('abstract') or 'Abstract unavailable')[:160]}...\n")

    if data.get("synthesis_table_markdown"):
        print("=" * 80)
        print("COMPARATIVE SYNTHESIS MATRIX")
        print("=" * 80)
        print(data["synthesis_table_markdown"])


def cmd_graph(args):
    print(f"[*] Exploring citation graph for seed: '{args.seed}' (Mode: {args.mode})...", file=sys.stderr)
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
        sc_str = f"🟢 {sc.get('supporting', 0)} Supp | 🔴 {sc.get('contrasting', 0)} Cont" if sc.get("total_citations", 0) > 0 else "Unavailable or zero; inspect record"
        print(f"{idx}. {w.get('title')} ({w.get('year')})")
        print(f"   DOI: {w.get('doi')} | scite.ai: {sc_str}")
        if w.get("open_access_pdf"):
            print(f"   PDF: {w.get('open_access_pdf')}")
        print()


def cmd_read(args):
    print(f"[*] Reading PDF: '{args.target}'...", file=sys.stderr)
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


def cmd_materials(args):
    from lit_discovery.materials import query_all_materials
    if not (args.formula or args.elements or args.mof):
        print("Error: Must provide at least one of --formula, --elements, or --mof.")
        sys.exit(1)

    print("[*] Querying materials repositories...", file=sys.stderr)
    data = query_all_materials(
        formula=args.formula,
        elements=args.elements,
        mof_name=args.mof,
        limit=args.limit
    )

    if args.json:
        print(json.dumps(data, indent=2))
        return

    dbs = data.get("databases", {})
    print("\n" + "=" * 60)
    print("ZERO-AUTHENTICATION MATERIALS DISCOVERY")
    print("=" * 60)

    mp = dbs.get("materials_project_optimade", {})
    if mp.get("status") == "success" and mp.get("materials"):
        print(f"\n[+] Materials Project (OPTIMADE v1) - {len(mp['materials'])} matches:")
        for m in mp["materials"][:3]:
            print(f"  • {m.get('material_id')}: {m.get('formula_pretty')} | nsites={m.get('nsites')} | spacegroup={m.get('spacegroup_symbol') or 'N/A'}")

    oqmd = dbs.get("oqmd", {})
    if oqmd.get("status") == "success" and oqmd.get("materials"):
        print(f"\n[+] OQMD (Northwestern University) - {len(oqmd['materials'])} matches:")
        for m in oqmd["materials"][:3]:
            dhf = f"{m.get('formation_energy_eV_atom'):.3f}" if m.get('formation_energy_eV_atom') is not None else "N/A"
            stab = f"{m.get('stability_eV_atom'):.3f}" if m.get('stability_eV_atom') is not None else "N/A"
            print(f"  • Entry #{m.get('entry_id')}: {m.get('name')} | Proto={m.get('prototype')} | Spacegroup={m.get('spacegroup')} | ΔHf={dhf} eV/atom | Stability={stab} eV/atom")
    elif oqmd.get("status") == "timeout":
        print("\n[-] OQMD (Northwestern University): Request timed out (large phase space).")

    c2db = dbs.get("c2db_2d_materials", {})
    if c2db.get("status") == "success" and c2db.get("materials"):
        print(f"\n[+] C2DB (2D Monolayers - DTU) - {len(c2db['materials'])} matches:")
        for m in c2db["materials"][:3]:
            print(f"  • C2DB #{m.get('c2db_id')}: {m.get('chemical_formula')} | Dim={m.get('dimension_types')} | Sites={m.get('nsites')}")

    mof = dbs.get("core_mofdb", {})
    if mof.get("status") == "success" and mof.get("mofs"):
        print(f"\n[+] CoRE MOF / MOFdb (Northwestern) - {len(mof['mofs'])} matches:")
        for m in mof["mofs"][:3]:
            print(f"  • {m.get('name')} ({m.get('database')}): Surface Area={m.get('surface_area_m2g')} m²/g | Void Fraction={m.get('void_fraction')} | PLD={m.get('pore_limiting_diameter_A')} Å | LCD={m.get('largest_cavity_diameter_A')} Å")

    print("\n" + "=" * 60)


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def main():
    parser = argparse.ArgumentParser(
        prog="lit-discovery",
        description="Search literature, explore citations, read PDFs, and export references."
    )
    parser.add_argument("-v", "--version", action="version", version=f"lit-discovery {__version__}")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Search
    p_search = subparsers.add_parser("search", help="Search scientific literature across 12 academic engines")
    p_search.add_argument("query", help="Scientific query string")
    p_search.add_argument("--engines", help="Comma-separated engine names (e.g. 'openalex,arxiv,crossref')")
    p_search.add_argument("--limit", type=positive_int, default=5, help="Results per engine (default: 5)")
    p_search.add_argument("--top", type=positive_int, default=10, help="Top enriched articles (default: 10)")
    p_search.add_argument("--no-enrich", action="store_true", help="Skip Unpaywall and scite.ai enrichment")
    p_search.add_argument("--bib", help="Path to save BibTeX (.bib) file")
    p_search.add_argument("--ris", help="Path to save RIS (.ris) file")
    p_search.add_argument("--json", action="store_true", help="Output full response as JSON")

    # Graph
    p_graph = subparsers.add_parser("graph", help="Explore related works, citing papers, or references")
    p_graph.add_argument("seed", help="Seed DOI or title")
    p_graph.add_argument("--mode", choices=["related", "forward", "backward"], default="related", help="Graph mode")
    p_graph.add_argument("--limit", type=positive_int, default=6, help="Max connected works")
    p_graph.add_argument("--json", action="store_true", help="Output as JSON")

    # Read
    p_read = subparsers.add_parser("read", help="Read a PDF and extract candidate material properties")
    p_read.add_argument("target", help="Target DOI or direct open-access PDF URL")
    p_read.add_argument("--pages", type=positive_int, default=30, help="Max pages to inspect (default: 30)")
    p_read.add_argument("--json", action="store_true", help="Output as JSON")

    # Materials
    p_mat = subparsers.add_parser("materials", help="Query zero-authentication structural materials databases (OQMD, C2DB, CoRE MOF, MP OPTIMADE)")
    p_mat.add_argument("--formula", help="Chemical formula (e.g. 'TiO2', 'MoS2', 'Fe2O3')")
    p_mat.add_argument("--elements", help="Comma-separated constituent elements (e.g. 'Ti,O')")
    p_mat.add_argument("--mof", help="MOF name or porous framework (e.g. 'UiO-66', 'MOF-5')")
    p_mat.add_argument("--limit", type=positive_int, default=5, help="Max items per database (default: 5)")
    p_mat.add_argument("--json", action="store_true", help="Output as raw JSON")

    args = parser.parse_args()

    if not args.command:
        print_banner()
        parser.print_help()
        sys.exit(0)

    handlers = {"search": cmd_search, "graph": cmd_graph, "read": cmd_read, "materials": cmd_materials}
    try:
        handlers[args.command](args)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
