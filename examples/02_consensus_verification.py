"""Example 2: Provider citation tallies (not scientific verification)."""
from lit_discovery import resolve_scite_tallies

def main():
    # Public DOI used as an example identifier
    doi = "10.1038/s41563-020-00831-2"
    print(f"[*] Fetching citation tallies for DOI: {doi}...")

    tallies = resolve_scite_tallies(doi)
    if not tallies:
        print("[-] Could not retrieve scite.ai data.")
        return

    print(f"\n[+] Provider citation classifications:")
    print(f"    • Total Citations: {tallies.get('total_citations')}")
    print(f"    • 🟢 Supporting Citations: {tallies.get('supporting')}")
    print(f"    • 🔴 Contrasting Citations: {tallies.get('contrasting')}")
    print(f"    • ⚪ Mentioning Citations: {tallies.get('mentioning')}")
    print(f"    • Citing Publications: {tallies.get('citing_publications')}")

    print("\nCitation classifications do not establish scientific consensus.")


if __name__ == "__main__":
    main()
