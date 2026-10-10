"""
FastAPI REST API bridge for chem-mat-hub to connect with ChatGPT Custom Actions.

Enables ChatGPT (via Custom GPT Actions) to execute high-precision thermophysical
equations of state (CoolProp), fetch polymer engineering specs (Zylon, Kevlar, Kapton, etc.),
query crystal & DFT databases (OQMD, AFLOW, C2DB, MOFdb), compute Walden ionicity,
and query 12 academic literature engines concurrently.
"""

import os
import sys
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Ensure the scripts directory is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

import codex_hub as runtime
import research
hub = runtime.hub

app = FastAPI(
    title="ChemMat Hub API",
    version="1.0.0",
    description=(
        "Unified chemistry, materials science, thermodynamics, polymer engineering, "
        "and literature discovery platform for ChatGPT."
    ),
)

# Allow CORS for ChatGPT
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", summary="Health Check")
def root():
    return {
        "status": "online",
        "service": "ChemMat Hub ChatGPT Action Server",
        "endpoints": [
            "/polymer",
            "/coolprop",
            "/walden",
            "/materials",
            "/substance",
            "/literature",
            "/citation-graph",
            "/deep-read",
            "/full-report"
        ]
    }

@app.get(
    "/polymer",
    summary="Query Polymer Engineering Specifications",
    description="Retrieve curated thermal, mechanical, chemical, and solvent properties for high-performance polymers (Zylon/PBO, Kevlar/PPTA, Kapton/PI, PVDF, PTFE, PEGDA, PEEK, Nafion)."
)
def get_polymer_specs(
    name: str = Query(..., description="Polymer name or acronym (e.g., 'zylon', 'pbo', 'kevlar', 'kapton', 'pvdf', 'nafion')")
) -> Dict[str, Any]:
    res = hub.query_polymer_specs(name)
    if "error" in res:
        raise HTTPException(status_code=404, detail=res["error"])
    return res

@app.get(
    "/coolprop",
    summary="Calculate Thermophysical Properties via CoolProp EOS",
    description="Calculate density, dynamic viscosity, isobaric heat capacity Cp, thermal conductivity, enthalpy, entropy, and phase state for 120+ fluids across specified Temperature (K) and Pressure (Pa)."
)
def calculate_coolprop(
    fluid: str = Query(..., description="Fluid name (e.g. 'Water', 'CO2', 'Ethanol', 'Methane', 'Nitrogen', 'Helium')"),
    temp_k: float = Query(298.15, description="Temperature in Kelvin (default: 298.15 K)"),
    pressure_pa: float = Query(101325.0, description="Pressure in Pascals (default: 101325.0 Pa, 1 atm)")
) -> Dict[str, Any]:
    res = hub.query_coolprop(fluid, T_K=temp_k, P_Pa=pressure_pa)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res

@app.get(
    "/walden",
    summary="Walden Plot & Ionicity Calculator",
    description="Calculate electrolyte molar conductivity, Walden product, deviation (Delta W), percentage ionicity, and ion-pairing dissociation regime (good ionic liquid, sub-ionic, poor)."
)
def calculate_walden(
    conductivity_ms_cm: float = Query(..., description="Electrolyte ionic conductivity in mS/cm"),
    viscosity_mpa_s: float = Query(..., description="Dynamic viscosity in mPa.s (cP)"),
    density_g_cm3: Optional[float] = Query(None, description="Optional density in g/cm3 for molar conductivity"),
    molar_mass: Optional[float] = Query(None, description="Optional molar mass in g/mol"),
    temp_k: float = Query(298.15, description="Temperature in Kelvin (default: 298.15 K)")
) -> Dict[str, Any]:
    result = hub.calculate_walden_ionicity(
        conductivity_mS_cm=conductivity_ms_cm,
        viscosity_mPa_s=viscosity_mpa_s,
        density_g_cm3=density_g_cm3,
        molar_mass=molar_mass,
        temperature_K=temp_k
    )
    if result.get('status') == 'error':
        raise HTTPException(status_code=422, detail=result.get('message') or result.get('error'))
    return result

@app.get(
    "/materials",
    summary="Query Materials, Crystals, and DFT Databases",
    description="Query DFT formation energies, convex hull stability, elastic moduli, 2D monolayers, or MOF porosity from OQMD, AFLOW, C2DB, and MOFdb."
)
def query_materials(
    formula: Optional[str] = Query(None, description="Chemical formula (e.g., 'Fe2O3', 'MoS2', 'TiO2', 'UiO-66')"),
    elements: Optional[str] = Query(None, description="Comma-separated constituent elements (e.g., 'Ti,O' or 'Fe,Ni')"),
    source: str = Query("oqmd", description="Target database: 'oqmd', 'aflow', 'c2db', 'mofdb', or 'all'")
) -> Dict[str, Any]:
    results = {}
    if source in ("oqmd", "all") and formula:
        results["oqmd"] = hub.query_oqmd(formula=formula, elements=elements)
    if source in ("aflow", "all"):
        results["aflow"] = hub.query_aflow(elements=elements, formula=formula)
    if source in ("c2db", "all") and formula:
        results["c2db"] = hub.query_c2db(formula=formula, elements=elements)
    if source in ("mofdb", "all") and formula:
        results["mofdb"] = hub.query_mofdb(name=formula)
    return results

@app.get(
    "/substance",
    summary="Query Chemical Substance, GHS Safety, and Kamlet-Taft Polarity",
    description="Retrieve PubChem physical properties, GHS hazard statements, Kamlet-Taft solvatochromic polarity (alpha, beta, pi*), and NIST WebBook thermochemistry."
)
def query_substance(
    name: str = Query(..., description="Chemical substance name or identifier (e.g., '[EMIM][TFSI]', 'benzene', 'NMP')")
) -> Dict[str, Any]:
    results = {}
    results["pubchem"] = hub.query_pubchem_experimental_and_ghs(name)
    results["kamlet_taft"] = hub.query_kamlet_taft(name)
    results["nist_webbook"] = hub.query_nist_webbook(name_or_formula=name)
    return results

@app.get(
    "/literature",
    summary="Multi-Source Academic Literature Discovery",
    description="Concurrently search 12 scholarly repositories (Semantic Scholar, Europe PMC, arXiv, OSTI, CORE, DOAJ, DataCite, PubMed, Zenodo, Scopus, OpenAlex, Crossref) with scite.ai consensus tallies and direct PDF links."
)
def search_literature(
    query: str = Query(..., description="Research search topic, compound, or keywords"),
    max_results: int = Query(50, ge=1, description="Maximum number of papers to return"),
    per_source: int = Query(30, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    max_pages: int = Query(10, ge=1),
    year_from: Optional[int] = Query(None),
    year_to: Optional[int] = Query(None),
    phrase: List[str] = Query([]),
    exclude: List[str] = Query([]),
    synonyms: List[str] = Query([]),
    sources: Optional[str] = Query(None),
    enrich: int = Query(8, ge=0),
    require_all: bool = Query(False),
    min_relevance: int = Query(1, ge=0, le=100)
) -> Dict[str, Any]:
    try:
        controls = research.Search(max_results, per_source, page_size, max_pages, year_from, year_to,
                                   tuple(phrase), tuple(exclude), tuple(synonyms),
                                   tuple(sources.split(',')) if sources else research.LITERATURE,
                                   enrich, require_all, min_relevance).validate()
        return research.search(hub, runtime, query, config=controls)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

@app.get(
    "/citation-graph",
    summary="Explore Citation Graph (Connected Papers Snowballing)",
    description="Snowball literature around a seed paper DOI. Mode can be 'related' (co-citation / Connected Papers style), 'forward' (citing works), or 'backward' (seminal references)."
)
def get_citation_graph(
    seed_doi: str = Query(..., description="Seed paper DOI (e.g. '10.1038/s41586-021-03819-2')"),
    mode: str = Query("related", description="'related', 'forward', or 'backward'")
) -> Dict[str, Any]:
    if mode not in ('related', 'forward', 'backward'):
        raise HTTPException(status_code=422, detail="mode must be related, forward or backward")
    return hub.explore_citation_graph(seed_doi, mode=mode)

@app.get(
    "/deep-read",
    summary="Retrieve and Deep-Read Full-Text PDF",
    description="Discover and retrieve public or campus-authorized paper PDF; return browser handoff when authentication is required. Parse PDF using PyMuPDF to extract experimental recipes, characterization parameters, and synthesis conditions."
)
def deep_read(
    doi_or_url: str = Query(..., description="Paper DOI or direct PDF URL"),
    max_pages: Optional[int] = Query(None, ge=1),
    ocr: bool = Query(False)
) -> Dict[str, Any]:
    if not (research.normalize_doi(doi_or_url) or doi_or_url.startswith(('https://', 'http://'))):
        raise HTTPException(status_code=422, detail='HTTP bridge accepts DOIs and URLs; use local CLI for local files')
    return hub.deep_read_pdf(doi_or_url, max_pages=max_pages, ocr=ocr)

@app.get(
    "/full-report",
    summary="Generate Comprehensive ChemMat Hub Report",
    description="Query all databases concurrently (PubChem, OQMD, AFLOW, Polymer Specs, CoolProp, Kamlet-Taft, Literature) for a compound or material."
)
def full_report(
    compound: str = Query(..., description="Compound, polymer, or material name")
) -> Dict[str, Any]:
    return hub.query_all(compound_name=compound)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting ChemMat Hub API on http://localhost:{port}")
    uvicorn.run("chatgpt_api_server:app", host=os.environ.get("CHEM_MAT_HUB_BIND", "127.0.0.1"), port=port)
