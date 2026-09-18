"""Comparative synthesis matrix generator (Elicit / SciSpace style)."""
from lit_discovery.synthesis.deep_reader import extract_material_properties

def generate_synthesis_matrix(articles):
    """Generates a structured side-by-side comparative table across discovered articles."""
    records = []
    md_lines = [
        "| Paper / Author | Key Polymer Host | Ionic Liquid / Electrolyte | Conductivity (σ) | Thermal Stability (Td) | Mechanical Modulus | Empirical Consensus (scite.ai) | Full-Text PDF |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
    ]
    for art in articles:
        title = art.get("title", "Untitled")
        authors = art.get("authors", [])
        author_label = authors[0] if authors else "Unknown"
        year = art.get("year") or "N/D"
        corpus = f"{title} {art.get('abstract', '')}"
        props = extract_material_properties(corpus)
        poly_str = ", ".join(props.get("polymer_matrix", [])) or "—"
        il_str = ", ".join(props.get("ionic_liquids", [])) or "—"
        cond_str = ", ".join(props.get("ionic_conductivity", [])) or "—"
        therm_str = ", ".join(props.get("thermal_properties", [])) or "—"
        mod_str = ", ".join(props.get("mechanical_modulus", []) + props.get("stretchability", [])) or "—"
        sc = art.get("smart_citations") or {}
        if sc and sc.get("total_citations", 0) > 0:
            sc_str = f"🟢 {sc.get('supporting', 0)} Supp / 🔴 {sc.get('contradicting', 0)} Cont"
        else:
            sc_str = "Neutral / 0"
        pdf_url = art.get("open_access_pdf")
        pdf_str = f"[Download PDF]({pdf_url})" if pdf_url else "—"
        records.append({
            "paper": f"{author_label} ({year})",
            "title": title,
            "polymer_matrix": props.get("polymer_matrix", []),
            "ionic_liquid": props.get("ionic_liquids", []),
            "ionic_conductivity": props.get("ionic_conductivity", []),
            "thermal_stability": props.get("thermal_properties", []),
            "mechanical_properties": props.get("mechanical_modulus", []) + props.get("stretchability", []),
            "smart_citations": sc,
            "doi": art.get("doi"),
            "open_access_pdf": pdf_url
        })
        display_title = (title[:45] + "...") if len(title) > 45 else title
        md_lines.append(
            f"| **{display_title}** <br>*{author_label} ({year})* | {poly_str} | {il_str} | {cond_str} | {therm_str} | {mod_str} | {sc_str} | {pdf_str} |"
        )
    return {
        "records": records,
        "markdown_table": "\n".join(md_lines)
    }
