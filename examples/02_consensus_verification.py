"""Example 2: Smart Citation Consensus (scite.ai) Empirical Verification."""
from lit_discovery import resolve_scite_tallies

def main():
    # Landmark Nature Materials ionogel paper
    doi = "10.1038/s41563-020-00831-2"
    print(f"[*] Fetching empirical smart citations for DOI: {doi}...")

    tallies = resolve_scite_tallies(doi)
    if not tallies:
        print("[-] Could not retrieve scite.ai data.")
        return

    print(f"\n[+] Empirical Research Sentiment:")
    print(f"    • Total Citations: {tallies.get('total_citations')}")
    print(f"    • 🟢 Supporting Citations: {tallies.get('supporting')}")
    print(f"    • 🔴 Contrasting Citations: {tallies.get('contrasting')}")
    print(f"    • ⚪ Mentioning Citations: {tallies.get('mentioning')}")
    print(f"    • Citing Publications: {tallies.get('citing_publications')}")

    ratio = (tallies.get('supporting', 0) / max(tallies.get('contrasting', 1), 1))
    print(f"\n[+] Consensus Ratio (Supporting / Contrasting): {ratio:.1f}x")

if __name__ == "__main__":
    main()
