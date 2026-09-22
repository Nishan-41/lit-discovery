"""Zero-Authentication Materials Project Client via OPTIMADE v1 protocol."""
import re
import requests

HEADERS = {"User-Agent": "lit-discovery/1.0 (academic-research-tool)"}

def formula_to_hill(formula: str) -> str:
    """Converts a chemical formula to Hill system notation for OPTIMADE queries.
    
    In the Hill system:
    - If Carbon (C) is present, C is written first, followed by H, then remaining elements alphabetically.
    - If no Carbon is present, all elements are ordered alphabetically.
    """
    if not formula:
        return formula
    tokens = re.findall(r'([A-Z][a-z]?)([0-9]*)', formula)
    counts = {}
    for el, count_str in tokens:
        counts[el] = counts.get(el, 0) + (int(count_str) if count_str else 1)
    if not counts:
        return formula
    hill_tokens = []
    if 'C' in counts:
        hill_tokens.append(('C', counts.pop('C')))
        if 'H' in counts:
            hill_tokens.append(('H', counts.pop('H')))
    for el in sorted(counts.keys()):
        hill_tokens.append((el, counts[el]))
    return "".join(f"{el}{count}" if count > 1 else el for el, count in hill_tokens)

def query_materials_project_optimade(formula: str = None, elements: str = None, limit: int = 5) -> dict:
    """Query Materials Project structure data using the public, zero-auth OPTIMADE v1 endpoint.
    
    Args:
        formula: Reduced chemical formula (e.g. 'TiO2', 'Fe2O3', 'MoS2')
        elements: Comma-separated list of elements (e.g. 'Ti,O')
        limit: Maximum number of structures to return (default 5)
        
    Returns:
        Dict with status, matched structures, and crystal lattice vectors.
    """
    try:
        url = "https://optimade.materialsproject.org/v1/structures"
        params = {"page_limit": limit}
        if formula:
            clean_form = formula.strip()
            hill_form = formula_to_hill(clean_form)
            if hill_form and hill_form != clean_form:
                params["filter"] = f'chemical_formula_reduced="{clean_form}" OR chemical_formula_hill="{clean_form}" OR chemical_formula_reduced="{hill_form}"'
            else:
                params["filter"] = f'chemical_formula_reduced="{clean_form}" OR chemical_formula_hill="{clean_form}"'
        elif elements:
            el_list = [e.strip() for e in elements.split(",") if e.strip()]
            params["filter"] = " AND ".join([f'elements HAS "{e}"' for e in el_list])
        else:
            return {"status": "skipped", "message": "No formula or elements provided."}

        r = requests.get(url, params=params, headers=HEADERS, timeout=12)
        if r.status_code == 200:
            data = r.json()
            structures = []
            for item in data.get("data", []):
                attr = item.get("attributes", {})
                structures.append({
                    "material_id": item.get("id"),
                    "formula_pretty": attr.get("chemical_formula_reduced"),
                    "nsites": attr.get("nsites"),
                    "elements": attr.get("elements"),
                    "lattice_vectors": attr.get("lattice_vectors"),
                    "spacegroup_symbol": attr.get("space_group_symbol_hermann_mauguin"),
                    "source": "Materials Project (Zero-Auth OPTIMADE)"
                })
            if structures:
                return {
                    "status": "success",
                    "total_matches": len(structures),
                    "materials": structures,
                    "provider": "Materials Project (OPTIMADE v1)"
                }
        return {"status": "not_found", "materials": []}
    except Exception as e:
        return {"status": "error", "error": str(e)}
