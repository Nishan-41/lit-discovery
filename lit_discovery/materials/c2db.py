"""Zero-Authentication DTU C2DB (Computational 2D Materials Database) Client via OPTIMADE."""
import requests
from lit_discovery.materials.optimade import formula_to_hill

HEADERS = {"User-Agent": "lit-discovery/1.0 (academic-research-tool)"}

def query_c2db(formula: str = None, elements: str = None, limit: int = 5) -> dict:
    """Query Technical University of Denmark (DTU) C2DB for 2D monolayer materials.
    
    Provides standardized OPTIMADE v1 queries for 2D monolayer structures,
    dimension types [1, 1, 0], lattice vectors, and stoichiometry.
    
    Args:
        formula: Chemical formula (e.g. 'MoS2', 'graphene', 'BN', 'TiO2')
        elements: Comma-separated elements (e.g. 'Mo,S')
        limit: Maximum results (default 5)
        
    Returns:
        Dict with status and matched 2D structures.
    """
    try:
        url = "https://c2db.fysik.dtu.dk/optimade/v1/structures"
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
            return {"status": "skipped", "message": "No formula or elements provided for C2DB query."}

        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            structures = []
            for item in data.get("data", []):
                attr = item.get("attributes", {})
                structures.append({
                    "c2db_id": item.get("id"),
                    "chemical_formula": attr.get("chemical_formula_reduced") or attr.get("chemical_formula_descriptive"),
                    "dimension_types": attr.get("dimension_types"),
                    "elements": attr.get("elements"),
                    "nsites": attr.get("nsites"),
                    "lattice_vectors": attr.get("lattice_vectors"),
                    "source": "C2DB (Technical University of Denmark)"
                })
            return {
                "status": "success",
                "total_returned": len(structures),
                "materials": structures,
                "provider": "C2DB (DTU / OPTIMADE v1)"
            }
        return {"status": "not_found", "materials": []}
    except Exception as e:
        return {"status": "error", "error": str(e)}
