"""Zero-Authentication OQMD (Open Quantum Materials Database) Client."""
import requests

HEADERS = {"User-Agent": "lit-discovery/1.0 (academic-research-tool)"}

def query_oqmd(formula: str = None, elements: str = None, limit: int = 5) -> dict:
    """Query Northwestern University's Open Quantum Materials Database (OQMD).
    
    Returns DFT formation energies, thermodynamic stability (distance to convex hull),
    crystal prototypes, space groups, volume, and unit cell lattice matrices.
    
    Args:
        formula: Chemical formula (e.g. 'Fe2O3', 'TiO2', 'LiCoO2')
        elements: Comma-separated elements (e.g. 'Fe,O')
        limit: Maximum results (default 5)
        
    Returns:
        Dict with status, matched structures, and calculated physical/electronic properties.
    """
    target = formula
    if not target and elements:
        target = "-".join([e.strip() for e in elements.split(",") if e.strip()])
    if not target:
        return {"status": "skipped", "message": "No formula or elements provided for OQMD query."}
    
    try:
        url = "https://oqmd.org/oqmdapi/formationenergy"
        params = {"composition": target.strip(), "limit": limit}
        r = requests.get(url, params=params, headers=HEADERS, timeout=20)
        if r.status_code == 200:
            data = r.json()
            raw_entries = data.get("data", [])
            entries = []
            for item in raw_entries:
                entries.append({
                    "entry_id": item.get("entry_id"),
                    "name": item.get("name"),
                    "composition": item.get("composition"),
                    "prototype": item.get("prototype"),
                    "spacegroup": item.get("spacegroup"),
                    "volume_ang3": item.get("volume"),
                    "band_gap_eV": item.get("band_gap"),
                    "formation_energy_eV_atom": item.get("delta_e"),
                    "stability_eV_atom": item.get("stability"),
                    "unit_cell": item.get("unit_cell"),
                    "source": "OQMD (Northwestern University)"
                })
            return {
                "status": "success",
                "total_returned": len(entries),
                "total_in_db": data.get("meta", {}).get("total_count"),
                "materials": entries,
                "provider": "OQMD (Northwestern University)"
            }
        return {"status": "not_found", "materials": []}
    except requests.exceptions.Timeout:
        return {"status": "timeout", "message": "OQMD query timed out (server load or large phase space).", "materials": []}
    except Exception as e:
        return {"status": "error", "error": str(e)}
