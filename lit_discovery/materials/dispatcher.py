"""Concurrent Multi-Database Dispatcher for Structural Materials."""
import concurrent.futures
from typing import Optional, Dict, Any

from lit_discovery.materials.optimade import query_materials_project_optimade
from lit_discovery.materials.oqmd import query_oqmd
from lit_discovery.materials.c2db import query_c2db
from lit_discovery.materials.mofdb import query_mofdb

def query_all_materials(
    formula: Optional[str] = None,
    elements: Optional[str] = None,
    mof_name: Optional[str] = None,
    limit: int = 5,
    max_workers: int = 4
) -> Dict[str, Any]:
    """Concurrently queries all zero-authentication structural materials databases:
    1. Materials Project via standardized OPTIMADE v1
    2. OQMD (Open Quantum Materials Database - Northwestern)
    3. C2DB (Computational 2D Materials Database - DTU)
    4. CoRE MOF / MOFdb (Northwestern University)
    
    Args:
        formula: Chemical formula (e.g. 'TiO2', 'MoS2', 'Fe2O3')
        elements: Comma-separated elements (e.g. 'Ti,O')
        mof_name: Name of MOF or porous material (e.g. 'UiO-66', 'MOF-5')
        limit: Max items per database
        max_workers: Thread pool concurrency limit
        
    Returns:
        Structured dictionary containing results from each materials repository.
    """
    results: Dict[str, Any] = {
        "query": {
            "formula": formula,
            "elements": elements,
            "mof_name": mof_name or formula
        },
        "databases": {}
    }
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        
        if formula or elements:
            futures["materials_project_optimade"] = executor.submit(
                query_materials_project_optimade, formula=formula, elements=elements, limit=limit
            )
            futures["oqmd"] = executor.submit(
                query_oqmd, formula=formula, elements=elements, limit=limit
            )
            futures["c2db_2d_materials"] = executor.submit(
                query_c2db, formula=formula, elements=elements, limit=limit
            )
            
        target_mof = mof_name or formula
        if target_mof:
            futures["core_mofdb"] = executor.submit(
                query_mofdb, name=target_mof, limit=limit
            )
            
        for key, fut in futures.items():
            try:
                results["databases"][key] = fut.result()
            except Exception as e:
                results["databases"][key] = {"status": "error", "error": str(e)}
                
    return results
