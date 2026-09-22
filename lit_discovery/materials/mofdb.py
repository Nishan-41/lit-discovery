"""Zero-Authentication Northwestern CoRE MOF / MOFdb Client."""
import requests

HEADERS = {"User-Agent": "lit-discovery/1.0 (academic-research-tool)"}

def query_mofdb(name: str = None, limit: int = 5) -> dict:
    """Query Northwestern University's CoRE MOF / MOFdb for porous crystalline frameworks.
    
    Returns gravimetric and volumetric surface areas (m2/g, m2/cm3), void fraction,
    pore limiting diameter (PLD), largest cavity diameter (LCD), and CIF availability.
    
    Args:
        name: Material or MOF name (e.g. 'UiO-66', 'MOF-5', 'HKUST-1', 'MIL-53')
        limit: Maximum results (default 5)
        
    Returns:
        Dict with status and matched porous frameworks.
    """
    if not name:
        return {"status": "skipped", "message": "No MOF name provided for MOFdb query."}
    try:
        url = "https://mof.tech.northwestern.edu/mofs.json"
        params = {"name_like": name.strip(), "per_page": limit}
        r = requests.get(url, params=params, headers=HEADERS, timeout=12)
        if r.status_code == 200:
            data = r.json()
            results = data.get("results", [])
            mofs = []
            for item in results[:limit]:
                mofs.append({
                    "mof_id": item.get("id"),
                    "name": item.get("name"),
                    "mofid": item.get("mofid"),
                    "surface_area_m2g": item.get("surface_area_m2g"),
                    "surface_area_m2cm3": item.get("surface_area_m2cm3"),
                    "void_fraction": item.get("void_fraction"),
                    "largest_cavity_diameter_A": item.get("lcd"),
                    "pore_limiting_diameter_A": item.get("pld"),
                    "database": item.get("database"),
                    "cif_available": bool(item.get("cif")),
                    "source": "CoRE MOF / MOFdb (Northwestern University)"
                })
            return {
                "status": "success",
                "total_returned": len(mofs),
                "mofs": mofs,
                "provider": "CoRE MOF / MOFdb (Northwestern University)"
            }
        return {"status": "not_found", "mofs": []}
    except Exception as e:
        return {"status": "error", "error": str(e)}
