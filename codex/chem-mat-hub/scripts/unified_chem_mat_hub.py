# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "beautifulsoup4", "python-dotenv", "pymupdf", "coolprop"]
# ///
"""Research-First Chemistry, Materials & Literature Discovery Hub.

Reconfigured for research substance over metrics:
- Extracts full structured abstracts (Background, Methods, Results, Conclusions)
- Full-text PDF deep reading and experimental section extraction via PyMuPDF
- Comparative Synthesis Matrix (Elicit/SciSpace style)
- Reference Management & BibTeX/RIS export for Zotero
- High-performance polymer engineering specifications (Zylon, Kevlar, Kapton, PVDF, etc.)
- CoolProp thermodynamic & transport properties equations of state
- NIST Chemistry WebBook thermochemical & Antoine vapor pressure parameters
- Duke AFLOW DFT elastic moduli & mechanical properties
- Walden plot electrolyte ionicity & dissociation calculator
- Computes query relevance rating (%)
- Eliminates citation counts, rankings, and bibliometric noise.
"""
import argparse
import concurrent.futures
import json
import math
import os
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv


try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    import CoolProp.CoolProp as CP
except ImportError:
    CP = None

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Process environment wins; optional explicit file then existing user setup.
if os.environ.get("CHEM_MAT_HUB_ENV_FILE"):
    load_dotenv(os.environ["CHEM_MAT_HUB_ENV_FILE"], override=False)
load_dotenv(os.path.expanduser("~/.env"), override=False)

MP_KEY = os.environ.get("MP_API_KEY")
RSC_KEY = os.environ.get("RSC_API_KEY")
SCOPUS_KEY = os.environ.get("SCOPUS_API_KEY") or os.environ.get("ELSEVIER_API_KEY")
CTX_KEY = os.environ.get("CTX_API_KEY") or os.environ.get("EPA_API_KEY")
S2_KEY = os.environ.get("S2_API_KEY") or os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
CORE_KEY = os.environ.get("CORE_API_KEY")

HEADERS = {"User-Agent": "Codex-ChemMatHub/1.0"}

# --- HELPER: ABSTRACT RECONSTRUCTION & RELEVANCE SCORING ---
def reconstruct_inverted_abstract(inverted_index):
    if not inverted_index:
        return None
    word_pos = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_pos.append((pos, word))
    word_pos.sort(key=lambda x: x[0])
    return " ".join([w for _, w in word_pos])

def clean_xml_abstract(xml_text):
    if not xml_text:
        return None
    text = re.sub(r"<[^>]+>", " ", xml_text)
    return " ".join(text.split()).strip()

def calculate_relevance_rating(query_terms, title, abstract):
    if not query_terms:
        return {"score_percent": 85, "relevance_level": "Relevant"}

    terms = [t.lower().strip() for t in re.split(r'[\s,\+\-]+', query_terms) if len(t.strip()) > 2]
    if not terms:
        return {"score_percent": 85, "relevance_level": "Relevant"}

    text_corpus = f"{title or ''} {abstract or ''}".lower()
    matches = sum(1 for t in terms if t in text_corpus)
    ratio = matches / len(terms)

    score = int(60 + (ratio * 38))
    score = min(score, 98)

    if score >= 90:
        level = "Highly Relevant (Direct Topic Match)"
    elif score >= 75:
        level = "Relevant (Related Material / Mechanism)"
    else:
        level = "Contextual (Background / Method Reference)"

    return {
        "score_percent": score,
        "relevance_level": level,
        "matched_keywords": [t for t in terms if t in text_corpus]
    }

def formula_to_hill(formula):
    """Converts a chemical formula to Hill system notation for OPTIMADE matching."""
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

def extract_material_properties(text):
    """Extracts materials science properties, metrics, and formulations from text."""
    props = {}
    if not text:
        return props

    cond = re.findall(r'(\d+(?:\.\d+)?(?:\s*[x×*]\s*10[−\-]?\d+)?\s*(?:mS|S|μS|uS)\s*[/·\s\-]*cm(?:[\^−\-]?1)?)', text, re.IGNORECASE)
    if cond:
        props['ionic_conductivity'] = list(dict.fromkeys(cond[:3]))

    temp = re.findall(r'((?:Td|Tg|Tm|decomposition\s+temp(?:erature)?|thermal\s+stability)[^.\n,;]*?[:=]?\s*[-+]?\d+(?:\.\d+)?\s*(?:°C|K|deg\s*C))', text, re.IGNORECASE)
    if not temp:
        temp = re.findall(r'([-+]?\d+(?:\.\d+)?\s*°C)', text)
    if temp:
        props['thermal_properties'] = list(dict.fromkeys(temp[:3]))

    mod = re.findall(r'((?:Young\'s\s+modulus|tensile\s+strength|elastic\s+modulus|modulus)[^.\n,;]*?[:=]?\s*\d+(?:\.\d+)?\s*(?:MPa|GPa|kPa))', text, re.IGNORECASE)
    if mod:
        props['mechanical_modulus'] = list(dict.fromkeys(mod[:3]))

    stretch = re.findall(r'((?:elongation|stretchability|strain\s+at\s+break)[^.\n,;]*?[:=]?\s*\d+(?:\.\d+)?\s*%)', text, re.IGNORECASE)
    if stretch:
        props['stretchability'] = list(dict.fromkeys(stretch[:3]))

    ils = re.findall(r'(\[(?:EMIM|BMIM|HMIM|OMIM|PMIM|Pyr\d+|PP\d+|DEME|BMPyr)\]\s*\[(?:TFSI|FSI|BF4|PF6|DCA|TfO|OTf|Cl|Br)\]|(?:EMIM|BMIM|HMIM|OMIM|Pyr\d+)\s*(?:TFSI|FSI|BF4|PF6|DCA|TfO))', text, re.IGNORECASE)
    if ils:
        props['ionic_liquids'] = list(dict.fromkeys(ils[:4]))

    polymers = re.findall(r'\b(PBO|Zylon|polybenzoxazole|PVDF(?:-HFP)?|PVA|PEGDA|PMMA|PEO|PDMS|polyimide|polyurethane|chitosan|cellulose)\b', text, re.IGNORECASE)
    if polymers:
        props['polymer_matrix'] = list(dict.fromkeys(p.upper() for p in polymers))

    solvents = re.findall(r'\b(NMP|DMF|DMAc|DMSO|THF|acetonitrile|methanol|ethanol|acetone|chloroform|toluene)\b', text, re.IGNORECASE)
    if solvents:
        props['solvents_or_reagents'] = list(dict.fromkeys(solvents[:4]))

    return props

def extract_sections_from_text(full_text):
    """Segment document text into standard scientific sections."""
    sections = {
        "abstract": "",
        "experimental_or_methods": "",
        "results_and_discussion": "",
        "conclusions": "",
        "raw_text_length": len(full_text)
    }
    headers = [
        ("experimental_or_methods", r'(?i)\n\s*(?:(?:1|2|3|4|5|6|I|II|III|IV|V)?\.?\s*(?:materials\s+and\s+methods|experimental\s+section|experimental\s+procedures?|methodology|experimental))\b'),
        ("results_and_discussion", r'(?i)\n\s*(?:(?:1|2|3|4|5|6|I|II|III|IV|V)?\.?\s*(?:results\s+and\s+discussion|results|discussion))\b'),
        ("conclusions", r'(?i)\n\s*(?:(?:1|2|3|4|5|6|I|II|III|IV|V)?\.?\s*(?:conclusions?|summary))\b')
    ]
    positions = []
    for sec_name, pat in headers:
        m = re.search(pat, full_text)
        if m:
            positions.append((m.start(), sec_name))

    positions.sort(key=lambda x: x[0])
    for idx, (pos, sec_name) in enumerate(positions):
        end_pos = positions[idx + 1][0] if idx + 1 < len(positions) else len(full_text)
        sec_chunk = full_text[pos:end_pos].strip()
        sections[sec_name] = sec_chunk[:8000]

    return sections

# --- SECTION 1: CHEMISTRY, SUBSTANCES & LABORATORY SAFETY ---
def query_pubchem_experimental_and_ghs(name_or_cid):
    """Fetches experimental physical properties and GHS safety data from PubChem PUG-View."""
    cid = name_or_cid
    try:
        if not str(name_or_cid).isdigit():
            c_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{urllib.parse.quote(str(name_or_cid))}/cids/JSON"
            r_c = requests.get(c_url, headers=HEADERS, timeout=8)
            if r_c.status_code == 200:
                cids = r_c.json().get("IdentifierList", {}).get("CID", [])
                if cids:
                    cid = cids[0]
                else:
                    return {"status": "not_found"}
            else:
                return {"status": "not_found"}

        exp_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON?heading=Experimental+Properties"
        r_exp = requests.get(exp_url, headers=HEADERS, timeout=10)
        exp_props = {}
        if r_exp.status_code == 200:
            def extract_from_sections(s_list):
                for s in s_list:
                    h = s.get("TOCHeading", "")
                    for info in s.get("Information", [])[:1]:
                        val = info.get("Value", {})
                        v_str = val.get("StringWithMarkup", [{}])[0].get("String")
                        if v_str and h in [
                            "Boiling Point", "Melting Point", "Flash Point", "Solubility",
                            "Density", "Vapor Pressure", "LogP", "Viscosity", "Surface Tension",
                            "Autoignition Temperature", "Refractive Index", "Dissociation Constants"
                        ]:
                            key = h.lower().replace(" ", "_")
                            if key not in exp_props:
                                exp_props[key] = v_str
                    if "Section" in s:
                        extract_from_sections(s["Section"])
            extract_from_sections(r_exp.json().get("Record", {}).get("Section", []))

        ghs_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON?heading=GHS+Classification"
        r_ghs = requests.get(ghs_url, headers=HEADERS, timeout=10)
        ghs_info = {"signal_word": None, "hazard_statements": []}
        if r_ghs.status_code == 200:
            def extract_ghs(s_list):
                for s in s_list:
                    for info in s.get("Information", []):
                        val = info.get("Value", {})
                        for sm in val.get("StringWithMarkup", []):
                            st = sm.get("String", "")
                            if st in ["Danger", "Warning"] and not ghs_info["signal_word"]:
                                ghs_info["signal_word"] = st
                            elif st.startswith("H") and ":" in st:
                                if st not in ghs_info["hazard_statements"]:
                                    ghs_info["hazard_statements"].append(st)
                    if "Section" in s:
                        extract_ghs(s["Section"])
            extract_ghs(r_ghs.json().get("Record", {}).get("Section", []))
            ghs_info["hazard_statements"] = ghs_info["hazard_statements"][:6]

        return {
            "status": "success",
            "cid": cid,
            "experimental_properties": exp_props,
            "ghs_safety": ghs_info
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

KAMLET_TAFT_DATABASE = {
    "[EMIM][TFSI]": {"alpha": 0.65, "beta": 0.24, "pi_star": 0.98, "class": "Ionic Liquid", "solvent_type": "Low basicity, high dipolarity, high conductivity electrolyte"},
    "[BMIM][TFSI]": {"alpha": 0.61, "beta": 0.24, "pi_star": 0.95, "class": "Ionic Liquid", "solvent_type": "Low basicity, hydrophobic electrolyte host"},
    "[BMIM][BF4]": {"alpha": 0.44, "beta": 0.38, "pi_star": 1.05, "class": "Ionic Liquid", "solvent_type": "Moderate basicity, very high dipolarity"},
    "[BMIM][PF6]": {"alpha": 0.41, "beta": 0.21, "pi_star": 1.03, "class": "Ionic Liquid", "solvent_type": "Hydrophobic, low basicity, high dipolarity"},
    "[HMIM][TFSI]": {"alpha": 0.58, "beta": 0.25, "pi_star": 0.92, "class": "Ionic Liquid", "solvent_type": "Hydrophobic long-chain ionic liquid"},
    "[EMIM][FSI]": {"alpha": 0.62, "beta": 0.27, "pi_star": 1.01, "class": "Ionic Liquid", "solvent_type": "Low viscosity, high ionic conductivity electrolyte"},
    "[BMPYR][TFSI]": {"alpha": 0.42, "beta": 0.24, "pi_star": 0.95, "class": "Ionic Liquid", "solvent_type": "Pyrrolidinium wide electrochemical stability window (>5V)"},
    "[PYR14][TFSI]": {"alpha": 0.42, "beta": 0.24, "pi_star": 0.95, "class": "Ionic Liquid", "solvent_type": "Pyrrolidinium battery & supercapacitor electrolyte"},
    "[EMIM][DCA]": {"alpha": 0.52, "beta": 0.64, "pi_star": 1.05, "class": "Ionic Liquid", "solvent_type": "Dicyanamide low viscosity, high conductivity"},
    "[EMIM][OAC]": {"alpha": 0.45, "beta": 1.20, "pi_star": 1.09, "class": "Ionic Liquid", "solvent_type": "High H-bond basicity, dissolves cellulose and natural polymers"},
    "[EMIM][OTF]": {"alpha": 0.63, "beta": 0.46, "pi_star": 1.00, "class": "Ionic Liquid", "solvent_type": "Triflate moderate basicity, high stability"},
    "NMP": {"alpha": 0.00, "beta": 0.76, "pi_star": 0.92, "class": "Polymer Solvent", "solvent_type": "Strong H-bond acceptor, excellent for PBO/polyimides"},
    "DMF": {"alpha": 0.00, "beta": 0.69, "pi_star": 0.88, "class": "Polymer Solvent", "solvent_type": "Dipolar aprotic solvent for PVDF casting"},
    "DMAC": {"alpha": 0.00, "beta": 0.76, "pi_star": 0.88, "class": "Polymer Solvent", "solvent_type": "Strong aprotic solvent for aromatic polymers"},
    "DMSO": {"alpha": 0.00, "beta": 0.76, "pi_star": 1.00, "class": "Polymer Solvent", "solvent_type": "High polarity, dissolves broad range of resins"},
    "WATER": {"alpha": 1.17, "beta": 0.18, "pi_star": 1.09, "class": "Aqueous", "solvent_type": "Strong H-bond donor, highly polar reference"},
    "ACETONE": {"alpha": 0.08, "beta": 0.48, "pi_star": 0.71, "class": "Volatile Solvent", "solvent_type": "Volatile co-solvent for phase inversion"},
    "PROPYLENE CARBONATE": {"alpha": 0.00, "beta": 0.40, "pi_star": 0.83, "class": "Battery Solvent", "solvent_type": "High dielectric constant (64), high boiling point"},
    "ETHYLENE CARBONATE": {"alpha": 0.00, "beta": 0.49, "pi_star": 0.90, "class": "Battery Solvent", "solvent_type": "High dielectric constant (89), solid at room temp"},
    "ACETONITRILE": {"alpha": 0.19, "beta": 0.31, "pi_star": 0.75, "class": "Organic Solvent", "solvent_type": "Low viscosity, high dielectric solvent for electrochemistry"},
    "ETHANOL": {"alpha": 0.83, "beta": 0.77, "pi_star": 0.54, "class": "Protic Solvent", "solvent_type": "Protic alcohol solvent"},
    "METHANOL": {"alpha": 0.93, "beta": 0.62, "pi_star": 0.60, "class": "Protic Solvent", "solvent_type": "Strong protic solvent"}
}

def query_kamlet_taft(name):
    """Returns Kamlet-Taft solvatochromic polarity parameters (alpha: hydrogen-bond acidity, beta: hydrogen-bond basicity, pi*: dipolarity/polarizability)."""
    if not name:
        return None
    clean = re.sub(r"[\s\-\_\[\]]", "", name.upper())
    for k, v in KAMLET_TAFT_DATABASE.items():
        k_clean = re.sub(r"[\s\-\_\[\]]", "", k.upper())
        if k_clean in clean or clean in k_clean:
            return {"status": "success", "substance": k, "parameters": v}
    return None

def query_pubchem(name_or_formula):
    """Queries PubChem for chemical identifiers, experimental physical properties, and GHS safety data."""
    try:
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{urllib.parse.quote(name_or_formula)}/property/MolecularFormula,MolecularWeight,CanonicalSMILES,InChIKey,IUPACName,XLogP,TPSA/JSON"
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code == 200:
            props = r.json().get("PropertyTable", {}).get("Properties", [])
            cid = props[0].get("CID") if props else None
            exp_data = query_pubchem_experimental_and_ghs(cid) if cid else {}
            return {
                "status": "success",
                "identifiers": props[:2],
                "experimental_properties": exp_data.get("experimental_properties", {}),
                "ghs_safety": exp_data.get("ghs_safety", {})
            }
        return {"status": "not_found", "identifiers": []}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def query_chemspider(compound_name):
    if not RSC_KEY:
        return {"status": "skipped", "message": "RSC_API_KEY not configured."}
    try:
        url = "https://api.rsc.org/compounds/v1/filter/name"
        r = requests.post(url, json={"name": compound_name}, headers={"apikey": RSC_KEY, "Content-Type": "application/json", **HEADERS}, timeout=12)
        if r.status_code == 200:
            qid = r.json().get("queryId")
            res_r = requests.get(f"https://api.rsc.org/compounds/v1/filter/{qid}/results", headers={"apikey": RSC_KEY, **HEADERS}, timeout=12)
            if res_r.status_code == 200:
                csids = res_r.json().get("results", [])[:3]
                if csids:
                    det_r = requests.post("https://api.rsc.org/compounds/v1/records/batch", json={"recordIds": csids, "fields": ["SMILES", "Formula", "InChIKey", "AverageMass"]}, headers={"apikey": RSC_KEY, "Content-Type": "application/json", **HEADERS}, timeout=12)
                    if det_r.status_code == 200:
                        return {"status": "success", "records": det_r.json().get("records", [])}
        return {"status": "not_found", "records": []}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def query_comptox(compound_name):
    if not CTX_KEY:
        return {"status": "skipped", "message": "CTX_API_KEY not configured."}
    try:
        url = f"https://comptox.epa.gov/ctx-api/chemical/search/equal/{urllib.parse.quote(compound_name)}"
        r = requests.get(url, headers={"x-api-key": CTX_KEY, "Accept": "application/json", **HEADERS}, timeout=12)
        if r.status_code == 200:
            items = r.json()
            if items:
                first = items[0]
                dtxsid = first.get("dtxsid")
                detail = {}
                if dtxsid:
                    det_url = f"https://comptox.epa.gov/ctx-api/chemical/detail/search/by-dtxsid/{dtxsid}"
                    r_det = requests.get(det_url, headers={"x-api-key": CTX_KEY, "Accept": "application/json", **HEADERS}, timeout=10)
                    if r_det.status_code == 200:
                        detail = r_det.json()
                return {
                    "status": "success",
                    "dtxsid": dtxsid,
                    "casrn": first.get("casrn") or detail.get("casrn"),
                    "preferred_name": first.get("preferredName") or detail.get("preferredName"),
                    "smiles": first.get("smiles") or detail.get("smiles"),
                    "molecular_weight": detail.get("molWeight"),
                    "mol_formula": detail.get("molFormula"),
                    "substance_type": detail.get("substanceType")
                }
        return {"status": "not_found"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

# --- SECTION 2: MATERIALS SCIENCE & SIMULATIONS ---
def query_materials_project_optimade(formula=None, elements=None, limit=5):
    """Zero-auth open queries to Materials Project via standardized OPTIMADE v1 protocol."""
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
                    "source": "Materials Project (Zero-Auth OPTIMADE)"
                })
            if structures:
                return {"status": "success", "total_matches": len(structures), "materials": structures, "mode": "Zero-Auth OPTIMADE"}
        return {"status": "not_found", "materials": []}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def query_materials_project(formula=None, elements=None):
    if not MP_KEY:
        return query_materials_project_optimade(formula=formula, elements=elements)
    try:
        params = {
            "_limit": 3,
            "_fields": "material_id,formula_pretty,symmetry,band_gap,formation_energy_per_atom,energy_above_hull,is_stable"
        }
        if formula:
            params["formula"] = formula
        if elements:
            params["elements"] = elements
        url = "https://api.materialsproject.org/materials/summary/"
        r = requests.get(url, headers={"X-API-KEY": MP_KEY, **HEADERS}, params=params, timeout=15)
        if r.status_code == 200:
            data = r.json().get("data", [])
            formatted = []
            for item in data[:3]:
                sym = item.get("symmetry", {})
                sym_str = sym.get("symbol") if isinstance(sym, dict) else str(sym)
                formatted.append({
                    "material_id": item.get("material_id"),
                    "formula_pretty": item.get("formula_pretty"),
                    "symmetry": sym_str,
                    "band_gap_eV": item.get("band_gap"),
                    "formation_energy_per_atom_eV": item.get("formation_energy_per_atom"),
                    "energy_above_hull_eV": item.get("energy_above_hull"),
                    "is_stable": item.get("is_stable")
                })
            return {"status": "success", "total_matches": len(data), "materials": formatted}
        return {"status": "not_found", "materials": []}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def query_nomad(formula=None, elements=None):
    try:
        query = {}
        if formula:
            query["results.material.chemical_formula_descriptive"] = formula
        if elements:
            query["results.material.elements"] = [e.strip() for e in elements.split(",") if e.strip()]
        payload = {"owner": "public", "pagination": {"page_size": 5}, "query": query}
        r = requests.post("https://nomad-lab.eu/prod/v1/api/v1/entries/query", json=payload, headers={"Content-Type": "application/json", **HEADERS}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            total = data.get("pagination", {}).get("total", 0)
            entries = []
            for entry in data.get("data", [])[:5]:
                mat = entry.get("results", {}).get("material", {})
                method = entry.get("results", {}).get("method", {}).get("simulation", {})
                entries.append({
                    "entry_id": entry.get("entry_id"),
                    "formula": mat.get("chemical_formula_descriptive") or mat.get("chemical_formula_hill"),
                    "program": method.get("program_name"),
                    "structural_type": mat.get("structural_type")
                })
            return {"status": "success", "total_simulations": total, "entries": entries}
        return {"status": "not_found", "entries": []}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def query_cod(elements=None, formula=None):
    try:
        params = {"format": "json", "limit": "5"}
        if elements:
            for idx, el in enumerate([e.strip() for e in elements.split(",") if e.strip()], start=1):
                params[f"el{idx}"] = el
        if formula:
            params["formula"] = formula
        url = "https://www.crystallography.net/cod/result?" + urllib.parse.urlencode(params)
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            structures = []
            for item in data[:5]:
                cod_id = item.get("file")
                structures.append({
                    "cod_id": cod_id,
                    "formula": item.get("formula"),
                    "spacegroup": item.get("spacegroup"),
                    "cell_a": item.get("a"),
                    "cell_b": item.get("b"),
                    "cell_c": item.get("c"),
                    "cif_url": f"https://www.crystallography.net/cod/{cod_id}.cif" if cod_id else None
                })
            return {"status": "success", "total_structures": len(data), "structures": structures}
        return {"status": "not_found", "structures": []}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def query_aflow(elements=None, formula=None):
    """Queries Duke University AFLOW AFLUX API for DFT-calculated elastic moduli, mechanical, and electronic properties."""
    try:
        species_list = []
        if elements:
            species_list = [e.strip() for e in elements.split(",") if e.strip()]
        elif formula:
            species_list = list(dict.fromkeys(re.findall(r"([A-Z][a-z]*)", formula)))

        if not species_list:
            return {"status": "skipped", "message": "No elements or formula provided for AFLOW query."}

        sp_str = ",".join(species_list)
        url = (
            f"https://aflow.org/API/aflux/?species({sp_str}),nspecies({len(species_list)}),"
            f"ael_bulk_modulus_voigt,ael_shear_modulus_voigt,ael_debye_temperature,Egap,enthalpy_formation_atom,paging(1)"
        )
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code == 200:
            data = r.json()
            entries = []
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, dict) and "compound" in v:
                        entries.append({
                            "compound": v.get("compound"),
                            "auid": v.get("auid"),
                            "aurl": v.get("aurl"),
                            "spacegroup": v.get("spacegroup_relax"),
                            "band_gap_eV": v.get("Egap"),
                            "enthalpy_formation_eV_atom": v.get("enthalpy_formation_atom"),
                            "bulk_modulus_voigt_GPa": v.get("ael_bulk_modulus_voigt"),
                            "shear_modulus_voigt_GPa": v.get("ael_shear_modulus_voigt"),
                            "debye_temperature_K": v.get("ael_debye_temperature")
                        })
                        if len(entries) >= 5:
                            break
            return {"status": "success", "total_returned": len(entries), "materials": entries}
        return {"status": "not_found", "materials": []}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def query_oqmd(formula=None, elements=None, limit=5):
    """Queries Northwestern University OQMD (Open Quantum Materials Database) for DFT formation energy, stability, and structure."""
    target = formula
    if not target and elements:
        target = "-".join([e.strip() for e in elements.split(",") if e.strip()])
    if not target:
        return {"status": "skipped", "message": "No formula or elements provided for OQMD query."}
    try:
        url = "https://oqmd.org/oqmdapi/formationenergy"
        params = {"composition": target, "limit": limit}
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
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
                "materials": entries
            }
        return {"status": "not_found", "materials": []}
    except requests.exceptions.Timeout:
        return {"status": "timeout", "message": "OQMD query timed out (server load or large phase space).", "materials": []}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def query_c2db(formula=None, elements=None, limit=5):
    """Queries DTU C2DB (Computational 2D Materials Database) via standardized OPTIMADE v1 for 2D monolayer structures."""
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

        r = requests.get(url, params=params, headers=HEADERS, timeout=12)
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
            return {"status": "success", "total_returned": len(structures), "materials": structures}
        return {"status": "not_found", "materials": []}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def query_mofdb(name=None, limit=5):
    """Queries CoRE MOF / MOFdb (Northwestern University) for porous crystalline frameworks, surface areas, and pore diameters."""
    if not name:
        return {"status": "skipped", "message": "No MOF name provided for MOFdb query."}
    try:
        url = "https://mof.tech.northwestern.edu/mofs.json"
        params = {"name_like": name.strip(), "per_page": limit}
        r = requests.get(url, params=params, headers=HEADERS, timeout=10)
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
            return {"status": "success", "total_returned": len(mofs), "mofs": mofs}
        return {"status": "not_found", "mofs": []}
    except Exception as e:
        return {"status": "error", "error": str(e)}

POLYMER_SPECS_DATABASE = {
    "ZYLON": {
        "chemical_name": "Poly(p-phenylene-2,6-benzobisoxazole)",
        "acronym": "PBO",
        "trade_names": ["Zylon", "Toyobo Zylon AS/HM"],
        "cas_number": "60393-27-3",
        "polymer_class": "Rigid-rod lyotropic liquid crystalline aromatic heterocyclic polymer",
        "mechanical_properties": {
            "tensile_strength_GPa": "5.8 GPa (filament), 3.5 - 4.5 GPa (yarn/fiber)",
            "tensile_modulus_GPa": "180 GPa (AS grade), 270 GPa (HM grade)",
            "elongation_at_break_pct": "2.5% (HM), 3.5% (AS)",
            "density_g_cm3": 1.56
        },
        "thermal_properties": {
            "thermal_decomposition_temp_Td_C": "650 °C (in N2), 550 °C (in air)",
            "continuous_service_temp_C": "350 - 400 °C",
            "limiting_oxygen_index_LOI_pct": "68% (highest flame resistance among synthetic fibers)"
        },
        "dielectric_and_physical": {
            "dielectric_constant": "3.0 (at 1 MHz)",
            "dielectric_loss_tangent": "0.002",
            "moisture_regain_pct": "0.6% (at 65% RH, 20 °C)"
        },
        "solubility_and_processing": {
            "chemical_resistance": "Inert to almost all organic solvents (alcohols, ketones, DMF, DMSO, NMP, chlorinated hydrocarbons) and dilute acids/bases.",
            "processing_solvents": "Dissolves only in strong protonating superacids: Polyphosphoric Acid (PPA, 82-84% P2O5), Methanesulfonic Acid (MSA), Chlorosulfonic acid, Trifluoromethanesulfonic acid.",
            "coagulation_baths": "Water, dilute phosphoric acid, or methanol (induces microphase separation into nanofibrillar networks)."
        },
        "role_in_ionogels_and_electrolytes": "Forms a rigid-rod nanofibrous skeleton providing extreme tensile modulus (>100 GPa) and thermal stability up to >500 °C while accommodating high ionic liquid loadings (>80 wt%) without mechanical collapse."
    },
    "KEVLAR": {
        "chemical_name": "Poly(p-phenylene terephthalamide)",
        "acronym": "PPTA",
        "trade_names": ["Kevlar 29", "Kevlar 49", "Twaron"],
        "cas_number": "24938-64-5",
        "polymer_class": "Aromatic polyamide (aramid)",
        "mechanical_properties": {
            "tensile_strength_GPa": "3.0 - 3.6 GPa",
            "tensile_modulus_GPa": "70 - 120 GPa",
            "elongation_at_break_pct": "2.4 - 3.6%",
            "density_g_cm3": 1.44
        },
        "thermal_properties": {
            "thermal_decomposition_temp_Td_C": "~500 °C",
            "continuous_service_temp_C": "180 - 250 °C",
            "limiting_oxygen_index_LOI_pct": "29%"
        },
        "dielectric_and_physical": {
            "dielectric_constant": "3.5 - 4.0",
            "moisture_regain_pct": "3.5 - 7.0%"
        },
        "solubility_and_processing": {
            "chemical_resistance": "Resistant to organic solvents, hydrocarbons, and oils; degraded by strong oxidizing acids.",
            "processing_solvents": "Concentrated sulfuric acid (H2SO4 >98%), or deprotonation via DMSO/KOH to form aramid nanofiber (ANF) hydrogels/organogels."
        },
        "role_in_ionogels_and_electrolytes": "Aramid nanofibers (ANF) deprotonated from Kevlar yield 3D porous hydrogel/ionogel scaffolds with high thermal cutoff and puncture resistance for battery separators."
    },
    "KAPTON": {
        "chemical_name": "Poly(4,4'-oxydiphenylene-pyromellitimide)",
        "acronym": "PI / PMDA-ODA",
        "trade_names": ["Kapton HN", "Apical", "Upilex"],
        "cas_number": "25038-81-7",
        "polymer_class": "Aromatic polyimide",
        "mechanical_properties": {
            "tensile_strength_MPa": "165 - 230 MPa",
            "tensile_modulus_GPa": "2.5 - 3.2 GPa",
            "elongation_at_break_pct": "60 - 85%",
            "density_g_cm3": 1.42
        },
        "thermal_properties": {
            "glass_transition_temp_Tg_C": "360 - 410 °C",
            "thermal_decomposition_temp_Td_C": ">520 °C",
            "continuous_service_temp_C": "-269 °C to 260 °C (short excursion to 400 °C)"
        },
        "dielectric_and_physical": {
            "dielectric_constant": "3.4 (at 1 kHz)",
            "dielectric_strength_kV_mm": ">200 kV/mm"
        },
        "solubility_and_processing": {
            "chemical_resistance": "Resistant to radiation, solvents, and fuels; susceptible to strong alkalis and steam hydrolysis.",
            "processing_solvents": "Processed via polyamic acid (PAA) precursor soluble in NMP, DMAc, or DMF; thermally imidized at 250 - 350 °C."
        },
        "role_in_ionogels_and_electrolytes": "Benchmark high-temperature flexible substrate and electrospun nanofiber matrix for ultra-wide-temperature ionic liquid electrolytes."
    },
    "PVDF": {
        "chemical_name": "Poly(vinylidene fluoride)",
        "acronym": "PVDF",
        "trade_names": ["Kynar", "Solef"],
        "cas_number": "24937-79-9",
        "polymer_class": "Semi-crystalline fluoropolymer",
        "mechanical_properties": {
            "tensile_strength_MPa": "35 - 55 MPa",
            "tensile_modulus_GPa": "1.5 - 2.5 GPa",
            "elongation_at_break_pct": "20 - 100%",
            "density_g_cm3": 1.78
        },
        "thermal_properties": {
            "melting_point_Tm_C": "165 - 175 °C",
            "glass_transition_temp_Tg_C": "-40 °C",
            "continuous_service_temp_C": "140 - 150 °C"
        },
        "dielectric_and_physical": {
            "dielectric_constant": "8.4 - 12.0 (high dielectric response, electroactive beta-phase)",
            "piezoelectric_coefficient_d33_pC_N": "-20 to -30 pC/N"
        },
        "solubility_and_processing": {
            "chemical_resistance": "Resistant to acids, halogens, and aliphatic hydrocarbons; dissolves in polar aprotic solvents.",
            "processing_solvents": "DMF, DMAc, NMP, Acetone, Cyclopentanone; fabricated via phase inversion (non-solvent induced phase separation, NIPS)."
        },
        "role_in_ionogels_and_electrolytes": "Most widely used polymer host for gel polymer electrolytes and ionogels; high dielectric constant promotes lithium and ionic liquid salt dissociation."
    },
    "PTFE": {
        "chemical_name": "Poly(tetrafluoroethylene)",
        "acronym": "PTFE",
        "trade_names": ["Teflon", "Fluon"],
        "cas_number": "9002-84-0",
        "polymer_class": "Fully fluorinated perfluoropolymer",
        "mechanical_properties": {
            "tensile_strength_MPa": "20 - 35 MPa",
            "tensile_modulus_GPa": "0.4 - 0.8 GPa",
            "elongation_at_break_pct": "200 - 400%",
            "density_g_cm3": 2.18
        },
        "thermal_properties": {
            "melting_point_Tm_C": "327 °C",
            "continuous_service_temp_C": "260 °C",
            "limiting_oxygen_index_LOI_pct": ">95%"
        },
        "dielectric_and_physical": {
            "dielectric_constant": "2.1 (ultralow dielectric loss tangent <0.0002)",
            "coefficient_of_friction": "0.05 - 0.10"
        },
        "solubility_and_processing": {
            "chemical_resistance": "Universal chemical inertness; unaffected by virtually all acids, bases, and solvents up to 260 °C.",
            "processing_solvents": "Insoluble in all known solvents below 300 °C; processed by powder compaction, ram extrusion, or expanded porous membrane (ePTFE)."
        },
        "role_in_ionogels_and_electrolytes": "Porous ePTFE membranes serve as mechanically robust, ultra-chemically inert porous hosts impregnated with ionic liquids for fuel cells and flow batteries."
    },
    "PEGDA": {
        "chemical_name": "Poly(ethylene glycol) diacrylate",
        "acronym": "PEGDA",
        "trade_names": ["PEG-diacrylate"],
        "cas_number": "26570-48-9",
        "polymer_class": "Acrylate-terminated hydrophilic telechelic macromer",
        "mechanical_properties": {
            "tensile_strength_MPa": "1 - 15 MPa (crosslink dependent)",
            "tensile_modulus_MPa": "5 - 150 MPa (tunable based on Mn: 250 to 10,000 g/mol)",
            "elongation_at_break_pct": "50 - 300%",
            "density_g_cm3": 1.12
        },
        "thermal_properties": {
            "glass_transition_temp_Tg_C": "-45 °C to -20 °C",
            "thermal_decomposition_temp_Td_C": "~250 °C"
        },
        "dielectric_and_physical": {
            "dielectric_constant": "5.0 - 7.5",
            "optical_transmittance_pct": ">90% (visible spectrum)"
        },
        "solubility_and_processing": {
            "chemical_resistance": "Hydrophilic 3D covalent network; swells extensively in polar solvents and ionic liquids without dissolving.",
            "processing_solvents": "Monomer soluble in water, ethanol, ionic liquids, DMSO; cured via UV photopolymerization (365 nm / 405 nm) with radical photoinitiators (LAP, Irgacure 2959)."
        },
        "role_in_ionogels_and_electrolytes": "Primary choice for in-situ photocurable, stretchable, transparent ionogels and ionic skin sensors with fast curing kinetics (<60 s)."
    },
    "PEEK": {
        "chemical_name": "Poly(ether ether ketone)",
        "acronym": "PEEK",
        "trade_names": ["Victrex PEEK", "KetaSpire"],
        "cas_number": "29658-26-2",
        "polymer_class": "Semi-crystalline high-performance aromatic polyketone",
        "mechanical_properties": {
            "tensile_strength_MPa": "90 - 100 MPa",
            "tensile_modulus_GPa": "3.6 - 4.1 GPa",
            "elongation_at_break_pct": "30 - 45%",
            "density_g_cm3": 1.30
        },
        "thermal_properties": {
            "glass_transition_temp_Tg_C": "143 °C",
            "melting_point_Tm_C": "343 °C",
            "continuous_service_temp_C": "250 °C",
            "limiting_oxygen_index_LOI_pct": "35%"
        },
        "dielectric_and_physical": {
            "dielectric_constant": "3.2 - 3.3",
            "wear_resistance": "Exceptional abrasion resistance"
        },
        "solubility_and_processing": {
            "chemical_resistance": "Outstanding chemical resistance; insoluble in all common organic solvents at room temperature.",
            "processing_solvents": "Soluble only in concentrated sulfuric acid (>96% H2SO4) or methanesulfonic acid; sulfonated to SPEEK for proton exchange membranes."
        },
        "role_in_ionogels_and_electrolytes": "Electrospun or porous sulfonated PEEK (SPEEK) membranes provide high mechanical modulus and dimensional stability for wide-temperature electrolytes."
    },
    "NAFION": {
        "chemical_name": "Tetrafluoroethylene-perfluoro-3,6-dioxa-4-methyl-7-octenesulfonic acid copolymer",
        "acronym": "PFSA / Nafion",
        "trade_names": ["Nafion 117", "Nafion 212", "Aquivion"],
        "cas_number": "31175-20-9",
        "polymer_class": "Perfluorosulfonic acid (PFSA) ionomer",
        "mechanical_properties": {
            "tensile_strength_MPa": "20 - 43 MPa",
            "tensile_modulus_MPa": "100 - 300 MPa",
            "elongation_at_break_pct": "150 - 250%",
            "density_g_cm3": 1.98
        },
        "thermal_properties": {
            "glass_transition_temp_Tg_C": "~110 °C",
            "thermal_decomposition_temp_Td_C": "~280 °C (desulfonation), ~400 °C (PTFE backbone)",
            "continuous_service_temp_C": "80 - 120 °C"
        },
        "dielectric_and_physical": {
            "equivalent_weight_EW": "1100 g/equiv (Nafion 117)",
            "proton_conductivity_S_cm": "~0.1 S/cm (at 100% RH, 80 °C)"
        },
        "solubility_and_processing": {
            "chemical_resistance": "Extremely resistant to chemical oxidation and reduction; swells in polar solvents.",
            "processing_solvents": "Dispersible in water/aliphatic alcohol mixtures under elevated autoclave conditions (200-250 °C, pressure)."
        },
        "role_in_ionogels_and_electrolytes": "Gold standard ion-selective membrane; forms composite ionogels with ionic liquids for anhydrous proton and lithium transport."
    }
}

def query_polymer_specs(name):
    """Retrieves curated engineering specifications for high-performance polymers (Zylon/PBO, Kevlar, Kapton, PVDF, PTFE, PEGDA, PEEK, Nafion)."""
    if not name:
        return None
    clean = re.sub(r"[\s\-\_\(\)\,\.]", "", name.upper())

    alias_map = {
        "ZYLON": "ZYLON", "PBO": "ZYLON", "POLYPHENYLENEBENZOBISOXAZOLE": "ZYLON", "POLYBENZOBISOXAZOLE": "ZYLON", "POLYBENZOXAZOLE": "ZYLON",
        "KEVLAR": "KEVLAR", "PPTA": "KEVLAR", "ARAMID": "KEVLAR", "TWARON": "KEVLAR", "POLYPHENYLENETEREPHTHALAMIDE": "KEVLAR",
        "KAPTON": "KAPTON", "POLYIMIDE": "KAPTON", "PI": "KAPTON", "PMDAODA": "KAPTON",
        "PVDF": "PVDF", "POLYVINYLIDENEFLUORIDE": "PVDF", "KYNAR": "PVDF", "SOLEF": "PVDF",
        "PTFE": "PTFE", "TEFLON": "PTFE", "POLYTETRAFLUOROETHYLENE": "PTFE",
        "PEGDA": "PEGDA", "POLYETHYLENEGLYCOLDIACRYLATE": "PEGDA", "PEGDIACRYLATE": "PEGDA",
        "PEEK": "PEEK", "POLYETHERETHERKETONE": "PEEK",
        "NAFION": "NAFION", "PFSA": "NAFION"
    }

    target_key = None
    for k, mapped in alias_map.items():
        if k in clean or clean in k:
            target_key = mapped
            break

    if target_key and target_key in POLYMER_SPECS_DATABASE:
        return {
            "status": "success",
            "polymer": target_key,
            "specifications": POLYMER_SPECS_DATABASE[target_key]
        }
    return {"status": "not_found", "query": name}

# --- SECTION 3: PHYSICAL CHEMISTRY & IONIC LIQUIDS ---
def query_ilthermo(compound_name):
    try:
        url = f"https://ilthermo.boulder.nist.gov/ILT2/ilsearch?cmp={urllib.parse.quote(compound_name)}&nc=1"
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code == 200:
            res = r.json().get("res", [])
            formatted = []
            for item in res[:5]:
                if len(item) >= 4:
                    formatted.append({
                        "set_id": item[0],
                        "citation": item[1],
                        "property": item[2],
                        "phase": item[3],
                        "data_points": item[7] if len(item) > 7 else None
                    })
            return {"status": "success", "total_sets": len(res), "datasets": formatted}
        return {"status": "not_found", "datasets": []}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def query_coolprop(fluid_name, T_K=298.15, P_Pa=101325.0):
    """Calculates thermodynamic, transport, and phase properties using CoolProp equations of state."""
    if CP is None:
        return {"status": "skipped", "message": "CoolProp is not installed or available in this environment."}
    try:
        aliases = {
            "water": "Water", "h2o": "Water",
            "co2": "CarbonDioxide", "carbon dioxide": "CarbonDioxide",
            "ethanol": "Ethanol", "c2h5oh": "Ethanol",
            "methanol": "Methanol", "ch3oh": "Methanol",
            "nitrogen": "Nitrogen", "n2": "Nitrogen",
            "oxygen": "Oxygen", "o2": "Oxygen",
            "argon": "Argon", "ar": "Argon",
            "methane": "Methane", "ch4": "Methane",
            "ethane": "Ethane", "propane": "Propane",
            "benzene": "Benzene", "toluene": "Toluene",
            "ammonia": "Ammonia", "nh3": "Ammonia",
            "r134a": "R134a", "air": "Air"
        }
        fluid = aliases.get(fluid_name.strip().lower(), fluid_name.strip())

        d = CP.PropsSI('D', 'T', T_K, 'P', P_Pa, fluid)
        v = CP.PropsSI('V', 'T', T_K, 'P', P_Pa, fluid)
        k = CP.PropsSI('L', 'T', T_K, 'P', P_Pa, fluid)
        cp = CP.PropsSI('C', 'T', T_K, 'P', P_Pa, fluid)
        cv = CP.PropsSI('O', 'T', T_K, 'P', P_Pa, fluid)
        h = CP.PropsSI('H', 'T', T_K, 'P', P_Pa, fluid)
        s = CP.PropsSI('S', 'T', T_K, 'P', P_Pa, fluid)
        a = CP.PropsSI('A', 'T', T_K, 'P', P_Pa, fluid)
        phase = CP.PhaseSI('T', T_K, 'P', P_Pa, fluid)

        tcrit = CP.PropsSI('Tcrit', fluid)
        pcrit = CP.PropsSI('Pcrit', fluid)
        molar_mass = CP.PropsSI('molar_mass', fluid)

        surface_tension = None
        try:
            surface_tension = CP.PropsSI('I', 'T', T_K, 'P', P_Pa, fluid)
        except Exception:
            pass

        return {
            "status": "success",
            "fluid": fluid,
            "state_conditions": {
                "temperature_K": round(T_K, 2),
                "temperature_C": round(T_K - 273.15, 2),
                "pressure_Pa": round(P_Pa, 1),
                "pressure_bar": round(P_Pa / 1e5, 3),
                "phase": phase
            },
            "properties": {
                "density_kg_m3": round(d, 4),
                "dynamic_viscosity_Pa_s": v,
                "dynamic_viscosity_mPa_s": round(v * 1000.0, 4),
                "thermal_conductivity_W_m_K": round(k, 5),
                "isobaric_heat_capacity_Cp_J_kg_K": round(cp, 2),
                "isochoric_heat_capacity_Cv_J_kg_K": round(cv, 2),
                "specific_enthalpy_kJ_kg": round(h / 1000.0, 2),
                "specific_entropy_kJ_kg_K": round(s / 1000.0, 4),
                "speed_of_sound_m_s": round(a, 2),
                "surface_tension_mN_m": round(surface_tension * 1000.0, 3) if surface_tension else None,
                "molar_mass_g_mol": round(molar_mass * 1000.0, 3)
            },
            "critical_point": {
                "critical_temperature_K": round(tcrit, 2),
                "critical_pressure_bar": round(pcrit / 1e5, 2)
            }
        }
    except Exception as e:
        return {"status": "error", "fluid": fluid_name, "error": str(e)}

def query_nist_webbook(name_or_formula=None, cas=None):
    """Scrapes NIST Chemistry WebBook for thermochemical data (formation/combustion enthalpy, heat capacity) and Antoine vapor pressure equations."""
    try:
        query_val = cas if cas else name_or_formula
        if not query_val:
            return {"status": "skipped", "message": "No name or CAS provided for NIST WebBook query."}

        if cas:
            url = f"https://webbook.nist.gov/cgi/cbook.cgi?ID={urllib.parse.quote(str(cas))}&Units=SI&cTG=on&cTC=on&cTP=on"
        else:
            url = f"https://webbook.nist.gov/cgi/cbook.cgi?Name={urllib.parse.quote(str(name_or_formula))}&Units=SI&cTG=on&cTC=on&cTP=on"

        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
        if r.status_code != 200 or "Not Found" in r.text:
            return {"status": "not_found", "message": f"NIST WebBook returned no record for {query_val}"}

        soup = BeautifulSoup(r.text, "html.parser")

        # Check if ambiguous name listing
        if "Search Results" in r.text and "cbook.cgi?ID=" in r.text:
            link = soup.find("a", href=re.compile(r"cbook\.cgi\?ID="))
            if link:
                sub_url = "https://webbook.nist.gov" + link["href"] + "&Units=SI&cTG=on&cTC=on&cTP=on"
                r = requests.get(sub_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
                soup = BeautifulSoup(r.text, "html.parser")

        data = {
            "status": "success",
            "query": query_val,
            "url": r.url,
            "thermochemical_data": {},
            "antoine_vapor_pressure": []
        }

        tables = soup.find_all("table")
        for t in tables:
            rows = t.find_all("tr")
            if not rows:
                continue
            header_cells = [c.text.strip() for c in rows[0].find_all(["th", "td"])]
            header_str = " ".join(header_cells).lower()

            # Antoine parameters table
            if "temperature (k)" in header_str and ("a" in header_cells or "a" in header_str):
                for row in rows[1:]:
                    cells = [c.text.strip() for c in row.find_all(["th", "td"])]
                    if len(cells) >= 4:
                        data["antoine_vapor_pressure"].append({
                            "temperature_range_K": cells[0],
                            "A": cells[1],
                            "B": cells[2],
                            "C": cells[3],
                            "reference": cells[4] if len(cells) > 4 else ""
                        })

            # Thermochemistry data (Quantity / Value / Units)
            elif "quantity" in header_str and "value" in header_str:
                for row in rows[1:]:
                    cells = [c.text.strip() for c in row.find_all(["th", "td"])]
                    if len(cells) >= 3 and cells[0] != "Quantity":
                        q = cells[0]
                        v = cells[1]
                        u = cells[2]
                        data["thermochemical_data"][q] = f"{v} {u}".strip()

        data["antoine_vapor_pressure"] = data["antoine_vapor_pressure"][:4]
        return data
    except Exception as e:
        return {"status": "error", "error": str(e)}

def calculate_walden_ionicity(conductivity_mS_cm, viscosity_mPa_s, density_g_cm3=None, molar_mass=None, temperature_K=298.15):
    """Calculates electrolyte Walden product, deviation from ideal KCl line (Delta W), percentage ionicity, and ion-pairing regime."""
    try:
        if conductivity_mS_cm is None or viscosity_mPa_s is None:
            return {"status": "error", "message": "Both conductivity (mS/cm) and viscosity (mPa.s) are required."}

        values = [conductivity_mS_cm, viscosity_mPa_s, temperature_K]
        if (density_g_cm3 is None) != (molar_mass is None):
            raise ValueError("Supply density and molar mass together.")
        values += [v for v in (density_g_cm3, molar_mass) if v is not None]
        if any(not math.isfinite(float(v)) or float(v) <= 0 for v in values):
            raise ValueError("All supplied Walden inputs must be finite and positive.")
        kappa_S_cm = float(conductivity_mS_cm) * 1e-3
        eta_mPa_s = float(viscosity_mPa_s)
        eta_poise = eta_mPa_s / 100.0  # 1 mPa.s = 0.01 Poise
        log_inv_eta = math.log10(1.0 / eta_poise)

        has_molar = bool(density_g_cm3 and molar_mass)
        if has_molar:
            density = float(density_g_cm3)
            mw = float(molar_mass)
            lambda_molar = (kappa_S_cm * mw) / density  # S.cm2/mol
            log_lambda = math.log10(lambda_molar)
            delta_w = log_lambda - log_inv_eta
            ionicity_pct = round((10.0 ** delta_w) * 100.0, 2)
        else:
            lambda_molar = None
            log_lambda = None
            delta_w = None
            ionicity_pct = None

        walden_product_apparent = round(kappa_S_cm * eta_poise, 6)

        # Classification regime
        if delta_w is not None:
            if delta_w >= -0.1:
                regime = "Ideal / Superionic (Minimal Ion-Pairing, Highly Dissociated)"
            elif delta_w >= -0.35:
                regime = "Good Ionic Liquid (Weak Ion-Pairing, Typical Dialkylimidazolium)"
            elif delta_w >= -0.7:
                regime = "Subionic / Intermediate Ion-Association (Significant Neutral Clusters)"
            else:
                regime = "Poor Ionic Liquid / Strong Ion-Pairing or Molecular Solute"
        else:
            regime = "Apparent Walden product calculated (provide density and molar mass for exact Delta W and % ionicity)"

        return {
            "status": "success",
            "input_parameters": {
                "specific_conductivity_mS_cm": conductivity_mS_cm,
                "viscosity_mPa_s": viscosity_mPa_s,
                "viscosity_Poise": round(eta_poise, 5),
                "density_g_cm3": density_g_cm3,
                "molar_mass_g_mol": molar_mass,
                "temperature_K": temperature_K
            },
            "interpretation": "Relative Walden index assumes log10(Lambda) = log10(1/eta_P), intercept 0. This is not a measured free-ion fraction or a validated KCl calibration. Density/MW conversion assumes a neat liquid; use electrolyte concentration for mixtures and ionogels.",
            "walden_metrics": {
                "molar_conductivity_Lambda_S_cm2_mol": round(lambda_molar, 4) if lambda_molar else None,
                "log10_inv_viscosity": round(log_inv_eta, 4),
                "log10_Lambda": round(log_lambda, 4) if log_lambda else None,
                "walden_product_apparent_S_cm_P": walden_product_apparent,
                "delta_W_deviation_from_ideal_KCl": round(delta_w, 4) if delta_w is not None else None,
                "ionicity_percent": ionicity_pct,
                "dissociation_regime": regime
            }
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

# --- SECTION 4: RESEARCH-FIRST LITERATURE & ABSTRACT DISCOVERY (NO METRICS) ---
def resolve_unpaywall_pdf(doi):
    """Resolves direct legal open-access PDF links for any DOI via Unpaywall API."""
    if not doi:
        return None
    contact = os.environ.get("CHEM_MAT_HUB_UNPAYWALL_EMAIL")
    if not contact:
        return None
    clean_doi = doi.replace("https://doi.org/", "").strip()
    try:
        r = requests.get(f"https://api.unpaywall.org/v2/{clean_doi}", params={"email": contact}, timeout=4)
        if r.status_code == 200:
            best = r.json().get("best_oa_location") or {}
            return best.get("url_for_pdf") or best.get("url")
    except Exception:
        pass
    return None

def deep_read_pdf(target_doi_or_url, max_pages=30):
    """Full-text deep reading of an open-access scientific paper using PyMuPDF (fitz).

    Extracts:
    - Text segmented into Experimental, Results, Discussion, Conclusions
    - Materials properties (conductivities, degradation temps, moduli, ionic liquids, polymers)
    - Key synthesis parameters and procedures
    """
    if not fitz:
        return {"status": "error", "message": "PyMuPDF (fitz) is not installed in the environment."}

    target = target_doi_or_url.strip()
    pdf_url = target

    # If DOI was provided, resolve direct PDF link via Unpaywall
    if "10." in target and not (target.startswith("http") and target.lower().endswith(".pdf")):
        resolved_pdf = resolve_unpaywall_pdf(target)
        if resolved_pdf:
            pdf_url = resolved_pdf
        else:
            return {
                "status": "not_found",
                "message": f"Could not locate an open-access PDF for DOI '{target}' via Unpaywall.",
                "doi": target
            }

    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(pdf_url, headers=headers, timeout=25)
        if r.status_code != 200:
            return {"status": "error", "message": f"Failed to download PDF from {pdf_url} (HTTP {r.status_code})"}

        doc = fitz.open(stream=r.content, filetype="pdf")
        total_pages = len(doc)
        pages_to_read = min(total_pages, max_pages)

        full_text_pages = []
        for i in range(pages_to_read):
            page_text = doc[i].get_text()
            if page_text:
                full_text_pages.append(page_text)

        full_text = "\n".join(full_text_pages)

        # Segment into sections
        sections = extract_sections_from_text(full_text)

        # Extract properties from experimental section & full text
        props = extract_material_properties(full_text)
        exp_props = extract_material_properties(sections.get("experimental_or_methods", ""))

        # Merge properties
        for k, v in exp_props.items():
            if k not in props:
                props[k] = v
            else:
                props[k] = list(dict.fromkeys(props[k] + v))

        return {
            "status": "success",
            "source_pdf_url": pdf_url,
            "target_query": target,
            "total_pages": total_pages,
            "pages_read": pages_to_read,
            "extracted_properties": props,
            "experimental_section_preview": sections.get("experimental_or_methods", "")[:2500],
            "results_preview": sections.get("results_and_discussion", "")[:2500],
            "total_characters_extracted": len(full_text)
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "target": target}

def fetch_openalex_literature(query_text):
    results = []
    try:
        url = f"https://api.openalex.org/works?search={urllib.parse.quote(query_text)}&per_page=5"
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code == 200:
            for w in r.json().get("results", []):
                doi = w.get("doi")
                title = w.get("title")
                inv_abs = w.get("abstract_inverted_index")
                abstract = reconstruct_inverted_abstract(inv_abs)
                authors = [a.get("author", {}).get("display_name") for a in w.get("authorships", []) if a.get("author", {}).get("display_name")]
                journal = w.get("primary_location", {}).get("source", {}).get("display_name")
                year = w.get("publication_year")
                oa_pdf = w.get("open_access", {}).get("oa_url")
                if title:
                    results.append({
                        "title": title,
                        "authors": authors[:5],
                        "journal": journal,
                        "year": year,
                        "doi": doi,
                        "abstract": abstract,
                        "open_access_pdf": oa_pdf,
                        "source_database": "OpenAlex"
                    })
    except Exception:
        pass
    return results

def fetch_semantic_scholar_literature(query_text):
    results = []
    try:
        headers = {"x-api-key": S2_KEY, **HEADERS} if S2_KEY else HEADERS
        fields = "title,authors,year,abstract,tldr,citationCount,influentialCitationCount,openAccessPdf,venue,externalIds"
        url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={urllib.parse.quote(query_text)}&limit=5&fields={fields}"
        r = requests.get(url, headers=headers, timeout=12)
        if r.status_code == 429:
            import time
            time.sleep(1.5)
            r = requests.get(url, headers=headers, timeout=12)
        if r.status_code == 200:
            for it in r.json().get("data", []):
                title = it.get("title")
                authors = [a.get("name") for a in it.get("authors", []) if a.get("name")]
                journal = it.get("venue")
                year = it.get("year")
                doi_val = it.get("externalIds", {}).get("DOI")
                doi = f"https://doi.org/{doi_val}" if doi_val else None
                tldr_dict = it.get("tldr")
                tldr = tldr_dict.get("text") if isinstance(tldr_dict, dict) else None
                abstract = it.get("abstract")
                oa_dict = it.get("openAccessPdf")
                oa_pdf = oa_dict.get("url") if isinstance(oa_dict, dict) else None
                if oa_pdf and not oa_pdf.strip():
                    oa_pdf = None
                if title:
                    results.append({
                        "title": title,
                        "authors": authors[:5],
                        "journal": journal,
                        "year": year,
                        "doi": doi,
                        "tldr": tldr,
                        "abstract": abstract,
                        "open_access_pdf": oa_pdf,
                        "source_database": "Semantic Scholar"
                    })
    except Exception:
        pass
    return results

def fetch_europe_pmc_literature(query_text):
    results = []
    try:
        url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        params = {
            "query": f"{query_text} OPEN_ACCESS:y",
            "format": "json",
            "resultType": "core",
            "pageSize": 5
        }
        r = requests.get(
            url,
            params=params,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept": "application/json"},
            timeout=12
        )
        if r.status_code == 200:
            for it in r.json().get("resultList", {}).get("result", []):
                title = it.get("title")
                author_str = it.get("authorString")
                authors = [a.strip() for a in author_str.split(",") if a.strip()] if author_str else []
                journal = it.get("journalTitle")
                year = it.get("pubYear")
                doi_val = it.get("doi")
                doi = f"https://doi.org/{doi_val}" if doi_val and not doi_val.startswith("http") else doi_val
                pmcid = it.get("pmcid")
                raw_abs = it.get("abstractText")
                abstract = clean_xml_abstract(raw_abs) if raw_abs else None
                oa_pdf = f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf" if pmcid else None
                if title:
                    results.append({
                        "title": title,
                        "authors": authors[:5],
                        "journal": journal,
                        "year": int(year) if str(year).isdigit() else year,
                        "doi": doi,
                        "pmcid": pmcid,
                        "abstract": abstract,
                        "open_access_pdf": oa_pdf,
                        "source_database": "Europe PMC"
                    })
    except Exception:
        pass
    return results

def fetch_arxiv_literature(query_text):
    results = []
    try:
        url = f"https://export.arxiv.org/api/query?search_query=all:{urllib.parse.quote(query_text)}&max_results=4"
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code == 200:
            root = ET.fromstring(r.text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns):
                title_elem = entry.find("atom:title", ns)
                title = title_elem.text.strip().replace("\n", " ") if title_elem is not None and title_elem.text else ""
                summary_elem = entry.find("atom:summary", ns)
                summary = summary_elem.text.strip().replace("\n", " ") if summary_elem is not None and summary_elem.text else ""
                published_elem = entry.find("atom:published", ns)
                year = published_elem.text[:4] if published_elem is not None and published_elem.text else None
                authors = []
                for a in entry.findall("atom:author", ns):
                    name_elem = a.find("atom:name", ns)
                    if name_elem is not None and name_elem.text:
                        authors.append(name_elem.text.strip())
                id_elem = entry.find("atom:id", ns)
                paper_id = id_elem.text.strip() if id_elem is not None and id_elem.text else None
                pdf_link = None
                for link in entry.findall("atom:link", ns):
                    if link.attrib.get("title") == "pdf":
                        pdf_link = link.attrib.get("href")
                if title:
                    results.append({
                        "title": title,
                        "authors": authors[:5],
                        "journal": "arXiv Preprint",
                        "year": int(year) if year and year.isdigit() else year,
                        "doi": paper_id,
                        "abstract": summary,
                        "open_access_pdf": pdf_link,
                        "source_database": "arXiv"
                    })
    except Exception:
        pass
    return results

def fetch_crossref_literature(query_text):
    results = []
    try:
        url = f"https://api.crossref.org/works?query={urllib.parse.quote(query_text)}&rows=4"
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code == 200:
            items = r.json().get("message", {}).get("items", [])
            for it in items:
                doi_str = it.get("DOI")
                doi_url = f"https://doi.org/{doi_str}" if doi_str and not doi_str.startswith("http") else doi_str
                title = it.get("title", [""])[0] if it.get("title") else ""
                xml_abs = it.get("abstract")
                abstract = clean_xml_abstract(xml_abs)
                authors = [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in it.get("author", []) if a.get("family")]
                journal = it.get("container-title", [""])[0] if it.get("container-title") else ""
                published = it.get("published-print", {}) or it.get("published-online", {}) or it.get("created", {})
                year = published.get("date-parts", [[None]])[0][0] if published.get("date-parts") else None
                if title:
                    results.append({
                        "title": title,
                        "authors": authors[:5],
                        "journal": journal,
                        "year": year,
                        "doi": doi_url,
                        "abstract": abstract,
                        "open_access_pdf": None,
                        "source_database": "Crossref"
                    })
    except Exception:
        pass
    return results

def fetch_scopus_literature(query_text):
    results = []
    if not SCOPUS_KEY:
        return results
    try:
        q_fmt = f"TITLE-ABS-KEY({query_text})"
        r = requests.get(
            "https://api.elsevier.com/content/search/scopus",
            headers={"X-ELS-APIKey": SCOPUS_KEY, "Accept": "application/json", **HEADERS},
            params={"query": q_fmt, "count": 4},
            timeout=12
        )
        if r.status_code == 200:
            entries = r.json().get("search-results", {}).get("entry", [])
            for it in entries:
                doi_str = it.get("prism:doi")
                doi_url = f"https://doi.org/{doi_str}" if doi_str else None
                title = it.get("dc:title")
                creator = it.get("dc:creator")
                journal = it.get("prism:publicationName")
                date = it.get("prism:coverDate")
                year = date[:4] if date else None

                # Retrieve real abstract via Elsevier Abstract Retrieval API
                abstract = None
                if doi_str:
                    try:
                        abs_url = f"https://api.elsevier.com/content/abstract/doi/{doi_str}"
                        r_abs = requests.get(
                            abs_url,
                            headers={"X-ELS-APIKey": SCOPUS_KEY, "Accept": "application/json", **HEADERS},
                            timeout=8
                        )
                        if r_abs.status_code == 200:
                            core = r_abs.json().get("abstracts-retrieval-response", {}).get("coredata", {})
                            dc_desc = core.get("dc:description")
                            if dc_desc:
                                abstract = clean_xml_abstract(dc_desc)
                    except Exception:
                        pass

                if title:
                    results.append({
                        "title": title,
                        "authors": [creator] if creator else [],
                        "journal": journal,
                        "year": int(year) if year and year.isdigit() else year,
                        "doi": doi_url,
                        "abstract": abstract or "Peer-reviewed article indexed in Scopus; full text accessible via DOI.",
                        "open_access_pdf": None,
                        "source_database": "Scopus (Elsevier)"
                    })
    except Exception:
        pass
    return results

def fetch_osti_literature(query_text):
    results = []
    try:
        url = "https://www.osti.gov/api/v1/records"
        params = {"term": query_text, "rows": 4}
        r = requests.get(url, params=params, headers={"Accept": "application/json", **HEADERS}, timeout=12)
        if r.status_code == 200:
            for it in r.json():
                title = it.get("title")
                authors_raw = it.get("authors", [])
                authors = [a.strip() for a in authors_raw if isinstance(a, str) and a.strip()]
                journal = it.get("journal_name") or it.get("product_type") or "DOE / OSTI Technical Report"
                pub_date = it.get("publication_date") or ""
                year = int(pub_date[:4]) if len(pub_date) >= 4 and pub_date[:4].isdigit() else None
                doi_str = it.get("doi")
                doi_url = f"https://doi.org/{doi_str}" if doi_str and not doi_str.startswith("http") else doi_str
                abstract = clean_xml_abstract(it.get("description"))

                oa_pdf = None
                for link in it.get("links", []):
                    if link.get("rel") == "fulltext":
                        oa_pdf = link.get("href")
                        break

                if title:
                    results.append({
                        "title": title,
                        "authors": authors[:5],
                        "journal": journal,
                        "year": year,
                        "doi": doi_url or (f"https://www.osti.gov/biblio/{it.get('osti_id')}" if it.get("osti_id") else None),
                        "abstract": abstract,
                        "open_access_pdf": oa_pdf,
                        "source_database": "OSTI.gov (DOE)"
                    })
    except Exception:
        pass
    return results

def fetch_doaj_literature(query_text):
    results = []
    try:
        url = f"https://doaj.org/api/v2/search/articles/{urllib.parse.quote(query_text)}?pageSize=4"
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code == 200:
            for it in r.json().get("results", []):
                bib = it.get("bibjson", {})
                title = bib.get("title")
                authors = [a.get("name") for a in bib.get("author", []) if a.get("name")]
                journal = bib.get("journal", {}).get("title") or "DOAJ Open Access Journal"
                year_str = bib.get("year")
                year = int(year_str) if str(year_str).isdigit() else None
                dois = [i.get("id") for i in bib.get("identifier", []) if i.get("type") == "doi"]
                doi = f"https://doi.org/{dois[0]}" if dois else None
                abstract = clean_xml_abstract(bib.get("abstract"))
                links = [l.get("url") for l in bib.get("link", []) if l.get("type") == "fulltext"]
                oa_pdf = links[0] if links else None
                if title:
                    results.append({
                        "title": title,
                        "authors": authors[:5],
                        "journal": journal,
                        "year": year,
                        "doi": doi,
                        "abstract": abstract,
                        "open_access_pdf": oa_pdf,
                        "source_database": "DOAJ (Open Access)"
                    })
    except Exception:
        pass
    return results

def fetch_datacite_literature(query_text):
    results = []
    try:
        url = f"https://api.datacite.org/dois?query={urllib.parse.quote(query_text)}&page[size]=4"
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code == 200:
            for it in r.json().get("data", []):
                attr = it.get("attributes", {})
                titles = attr.get("titles", [])
                title = titles[0].get("title") if titles else ""
                creators = [c.get("name") for c in attr.get("creators", []) if c.get("name")]
                res_type = attr.get("types", {}).get("resourceTypeGeneral") or "Dataset/Thesis"
                publisher = attr.get("publisher") or "DataCite Repository"
                journal = f"{publisher} ({res_type})"
                year = attr.get("publicationYear")
                doi_str = attr.get("doi")
                doi = f"https://doi.org/{doi_str}" if doi_str and not doi_str.startswith("http") else doi_str
                descriptions = attr.get("descriptions", [])
                abstract = clean_xml_abstract(descriptions[0].get("description")) if descriptions else None
                if title:
                    results.append({
                        "title": title,
                        "authors": creators[:5],
                        "journal": journal,
                        "year": int(year) if str(year).isdigit() else None,
                        "doi": doi,
                        "abstract": abstract,
                        "open_access_pdf": None,
                        "source_database": "DataCite"
                    })
    except Exception:
        pass
    return results

def fetch_pubmed_literature(query_text):
    results = []
    try:
        search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={urllib.parse.quote(query_text)}&retmode=json&retmax=4"
        r_search = requests.get(search_url, headers=HEADERS, timeout=10)
        if r_search.status_code == 200:
            id_list = r_search.json().get("esearchresult", {}).get("idlist", [])
            if id_list:
                sum_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={','.join(id_list)}&retmode=json"
                r_sum = requests.get(sum_url, headers=HEADERS, timeout=10)
                if r_sum.status_code == 200:
                    data = r_sum.json().get("result", {})
                    for pid in id_list:
                        doc = data.get(pid, {})
                        title = doc.get("title")
                        authors = [a.get("name") for a in doc.get("authors", []) if a.get("name")]
                        journal = doc.get("source") or "PubMed Indexed Journal"
                        pubdate = doc.get("pubdate") or ""
                        year = int(pubdate[:4]) if len(pubdate) >= 4 and pubdate[:4].isdigit() else None

                        doi = None
                        pmcid = None
                        for aid in doc.get("articleids", []):
                            if aid.get("idtype") == "doi":
                                doi = f"https://doi.org/{aid.get('value')}"
                            elif aid.get("idtype") in ["pmc", "pmcid"]:
                                val = aid.get("value", "")
                                pmcid = val if val.startswith("PMC") else f"PMC{val}"

                        oa_pdf = f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf" if pmcid else None
                        if title:
                            results.append({
                                "title": title,
                                "authors": authors[:5],
                                "journal": journal,
                                "year": year,
                                "doi": doi or f"https://pubmed.ncbi.nlm.nih.gov/{pid}/",
                                "abstract": None,
                                "open_access_pdf": oa_pdf,
                                "source_database": "PubMed (NLM)"
                            })
    except Exception:
        pass
    return results

def fetch_core_literature(query_text):
    results = []
    if not CORE_KEY:
        return results
    try:
        url = f"https://api.core.ac.uk/v3/search/works?q={urllib.parse.quote(query_text)}&limit=4"
        r = requests.get(url, headers={"Authorization": f"Bearer {CORE_KEY}", **HEADERS}, timeout=12)
        if r.status_code == 200:
            for it in r.json().get("results", []):
                title = it.get("title")
                authors = [a.get("name") for a in it.get("authors", []) if a.get("name")]
                journal = it.get("publisher") or "CORE Academic Repository"
                year = it.get("yearPublished")
                doi_val = it.get("doi")
                doi = f"https://doi.org/{doi_val}" if doi_val and not doi_val.startswith("http") else doi_val
                abstract = clean_xml_abstract(it.get("abstract"))
                oa_pdf = it.get("downloadUrl")
                if title:
                    results.append({
                        "title": title,
                        "authors": authors[:5],
                        "journal": journal,
                        "year": int(year) if year and str(year).isdigit() else None,
                        "doi": doi or (f"https://core.ac.uk/works/{it.get('id')}" if it.get("id") else None),
                        "abstract": abstract,
                        "open_access_pdf": oa_pdf,
                        "source_database": "CORE (Repositories)"
                    })
    except Exception:
        pass
    return results

def fetch_zenodo_literature(query_text):
    """Fetches open-access papers, theses, preprints, and datasets from CERN Zenodo."""
    results = []
    try:
        url = "https://zenodo.org/api/records"
        params = {"q": query_text, "size": 4, "sort": "bestmatch"}
        r = requests.get(url, params=params, headers=HEADERS, timeout=12)
        if r.status_code == 200:
            hits = r.json().get("hits", {}).get("hits", [])
            for hit in hits:
                meta = hit.get("metadata", {})
                title = meta.get("title")
                creators = [c.get("name") for c in meta.get("creators", []) if c.get("name")]
                pub_date = meta.get("publication_date") or ""
                year = int(pub_date[:4]) if len(pub_date) >= 4 and pub_date[:4].isdigit() else None
                doi_str = hit.get("doi") or meta.get("doi")
                doi = f"https://doi.org/{doi_str}" if doi_str and not str(doi_str).startswith("http") else doi_str
                res_type = meta.get("resource_type", {}).get("title") or "Open Research Record"
                journal = f"Zenodo ({res_type})"
                raw_desc = meta.get("description")
                abstract = clean_xml_abstract(raw_desc) if raw_desc else None

                oa_pdf = None
                files = hit.get("files", [])
                for f in files:
                    f_link = f.get("links", {}).get("self")
                    key_lower = f.get("key", "").lower()
                    if f_link and (f.get("type") == "pdf" or key_lower.endswith(".pdf") or "content" in f_link):
                        oa_pdf = f_link
                        break

                if title:
                    results.append({
                        "title": title,
                        "authors": creators[:5],
                        "journal": journal,
                        "year": year,
                        "doi": doi or hit.get("links", {}).get("self_html"),
                        "abstract": abstract,
                        "open_access_pdf": oa_pdf,
                        "source_database": "Zenodo (CERN)"
                    })
    except Exception:
        pass
    return results

def resolve_scite_tallies(doi):
    """Fetches smart citation sentiment metrics (supporting, contrasting, mentioning) from scite.ai."""
    if not doi:
        return None
    clean_doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
    if not clean_doi or not ("10." in clean_doi):
        return None
    try:
        r = requests.get(f"https://api.scite.ai/tallies/{clean_doi}", headers=HEADERS, timeout=4)
        if r.status_code == 200:
            data = r.json()
            return {
                "total_citations": data.get("total", 0),
                "supporting": data.get("supporting", 0),
                "contrasting": data.get("contradicting", 0),
                "mentioning": data.get("mentioning", 0),
                "citing_publications": data.get("citingPublications", 0)
            }
    except Exception:
        pass
    return None

def explore_citation_graph(seed_doi_or_query, mode="related", limit=6):
    """Explores the citation network around a seed paper (Connected Papers & Snowballing).

    Modes:
    - 'related': Bibliographically coupled & co-cited works (Connected Papers style)
    - 'forward' / 'cites': Works citing this seed paper (forward snowballing)
    - 'backward' / 'cited_by': Foundational works cited by this seed paper (backward snowballing)
    """
    clean_target = seed_doi_or_query.strip()
    wid = None
    seed_title = clean_target

    try:
        if "10." in clean_target:
            m = re.search(r'(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)', clean_target)
            doi = m.group(1) if m else clean_target.replace("https://doi.org/", "")
            r = requests.get(f"https://api.openalex.org/works/https://doi.org/{doi}", headers=HEADERS, timeout=10)
            if r.status_code == 200:
                work_data = r.json()
                wid = work_data.get("id", "").split("/")[-1]
                seed_title = work_data.get("title", seed_title)
        else:
            r = requests.get(f"https://api.openalex.org/works?search={urllib.parse.quote(clean_target)}&per_page=1", headers=HEADERS, timeout=10)
            if r.status_code == 200:
                results = r.json().get("results", [])
                if results:
                    wid = results[0].get("id", "").split("/")[-1]
                    seed_title = results[0].get("title", seed_title)
    except Exception:
        pass

    if not wid:
        return {
            "status": "not_found",
            "seed_query": clean_target,
            "message": "Could not resolve seed work in OpenAlex graph."
        }

    filter_key = "related_to"
    if mode in ["forward", "cites"]:
        filter_key = "cites"
    elif mode in ["backward", "cited_by", "references"]:
        filter_key = "cited_by"

    results = []
    try:
        url = f"https://api.openalex.org/works?filter={filter_key}:{wid}&per-page={limit}"
        r_graph = requests.get(url, headers=HEADERS, timeout=12)
        if r_graph.status_code == 200:
            for w in r_graph.json().get("results", []):
                doi = w.get("doi")
                title = w.get("title")
                inv_abs = w.get("abstract_inverted_index")
                abstract = reconstruct_inverted_abstract(inv_abs)
                authors = [a.get("author", {}).get("display_name") for a in w.get("authorships", []) if a.get("author", {}).get("display_name")]
                journal = w.get("primary_location", {}).get("source", {}).get("display_name")
                year = w.get("publication_year")
                oa_pdf = w.get("open_access", {}).get("oa_url")

                scite_info = resolve_scite_tallies(doi) if doi else None

                results.append({
                    "title": title,
                    "authors": authors[:5],
                    "journal": journal,
                    "year": year,
                    "doi": doi,
                    "abstract": abstract or "Abstract unavailable from this source; full text not yet verified.",
                    "open_access_pdf": oa_pdf,
                    "smart_citations": scite_info,
                    "graph_relationship": filter_key
                })
    except Exception as e:
        return {"status": "error", "error": str(e)}

    return {
        "status": "success",
        "seed_work": {
            "openalex_id": wid,
            "title": seed_title,
            "query": clean_target
        },
        "graph_mode": filter_key,
        "total_connected_works": len(results),
        "connected_works": results
    }

def generate_synthesis_matrix(articles):
    """Generates an Elicit/SciSpace-style comparative synthesis matrix across articles."""
    records = []
    md_lines = [
        "| Paper (Year) | Host Polymer | Ionic Liquid | Ionic Conductivity | Thermal Stability | Mechanical Modulus | scite.ai Consensus | OA PDF |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: |"
    ]

    for art in articles:
        title = art.get("title", "Untitled")
        authors = art.get("authors", [])
        first_author = authors[0].split()[-1] if authors else "Author"
        author_label = f"{first_author} et al." if len(authors) > 1 else first_author
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
            sc_str = f"🟢 {sc.get('supporting', 0)} Supp / 🔴 {sc.get('contrasting', 0)} Cont"
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

def fetch_doi_citation_metadata(doi, format_type="bibtex"):
    """Fetches official publisher citation metadata via DOI content negotiation."""
    if not doi:
        return None
    clean_doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
    if not clean_doi or "10." not in clean_doi:
        return None

    mime = "application/x-bibtex" if format_type == "bibtex" else "application/x-research-info-systems"
    try:
        r = requests.get(f"https://doi.org/{clean_doi}", headers={"Accept": mime, **HEADERS}, timeout=8)
        if r.status_code == 200 and r.text.strip():
            return r.text.strip()
    except Exception:
        pass
    return None

def export_zotero_references(articles, bib_path=None, ris_path=None):
    """Exports articles into BibTeX (.bib) and RIS (.ris) formats for Zotero and reference managers."""
    bib_entries = []
    ris_entries = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        bib_futs = {}
        ris_futs = {}
        for idx, a in enumerate(articles):
            doi = a.get("doi")
            if doi and "10." in doi:
                if bib_path:
                    bib_futs[idx] = ex.submit(fetch_doi_citation_metadata, doi, "bibtex")
                if ris_path:
                    ris_futs[idx] = ex.submit(fetch_doi_citation_metadata, doi, "ris")

        for idx, a in enumerate(articles):
            doi = a.get("doi")
            title = a.get("title", "Untitled")
            authors = a.get("authors", [])
            author_str = " and ".join(authors) if authors else "Unknown"
            year = a.get("year") or 2024
            journal = a.get("journal") or "Academic Publication"

            if bib_path:
                entry = None
                if idx in bib_futs:
                    try:
                        entry = bib_futs[idx].result()
                    except Exception:
                        pass
                if not entry:
                    cite_key = f"{(authors[0].split()[-1] if authors else 'Ref')}_{year}_{idx}"
                    clean_key = re.sub(r'[^a-zA-Z0-9_]', '', cite_key)
                    entry = (
                        f"@article{{{clean_key},\n"
                        f"  title={{{title}}},\n"
                        f"  author={{{author_str}}},\n"
                        f"  journal={{{journal}}},\n"
                        f"  year={{{year}}}"
                        + (f",\n  doi={{{doi}}}" if doi else "")
                        + "\n}"
                    )
                bib_entries.append(entry)

            if ris_path:
                entry = None
                if idx in ris_futs:
                    try:
                        entry = ris_futs[idx].result()
                    except Exception:
                        pass
                if not entry:
                    lines = [
                        "TY  - JOUR",
                        f"TI  - {title}",
                        f"JO  - {journal}",
                        f"PY  - {year}"
                    ]
                    for aut in authors:
                        lines.append(f"AU  - {aut}")
                    if doi:
                        lines.append(f"DO  - {doi}")
                    lines.append("ER  - ")
                    entry = "\n".join(lines)
                ris_entries.append(entry)

    if bib_path and bib_entries:
        full_bib = "\n\n".join(bib_entries)
        with open(bib_path, "w", encoding="utf-8") as f:
            f.write(full_bib)

    if ris_path and ris_entries:
        full_ris = "\n\n".join(ris_entries)
        with open(ris_path, "w", encoding="utf-8") as f:
            f.write(full_ris)

    return {
        "bibtex_count": len(bib_entries),
        "ris_count": len(ris_entries),
        "bib_path": bib_path,
        "ris_path": ris_path
    }

def query_research_literature(query_text):
    """Fetches structured abstracts from 12 discovery engines and enriches with scite.ai Smart Citations & Unpaywall."""
    raw_articles = []

    # Concurrent multi-engine retrieval across 12 databases
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        f_s2 = executor.submit(fetch_semantic_scholar_literature, query_text)
        f_epmc = executor.submit(fetch_europe_pmc_literature, query_text)
        f_arxiv = executor.submit(fetch_arxiv_literature, query_text)
        f_oa = executor.submit(fetch_openalex_literature, query_text)
        f_cr = executor.submit(fetch_crossref_literature, query_text)
        f_scopus = executor.submit(fetch_scopus_literature, query_text)
        f_osti = executor.submit(fetch_osti_literature, query_text)
        f_doaj = executor.submit(fetch_doaj_literature, query_text)
        f_dc = executor.submit(fetch_datacite_literature, query_text)
        f_pm = executor.submit(fetch_pubmed_literature, query_text)
        f_core = executor.submit(fetch_core_literature, query_text)
        f_zenodo = executor.submit(fetch_zenodo_literature, query_text)

        all_futures = [f_s2, f_epmc, f_arxiv, f_oa, f_cr, f_scopus, f_osti, f_doaj, f_dc, f_pm, f_core, f_zenodo]
        for fut in all_futures:
            try:
                res = fut.result()
                if res:
                    raw_articles.extend(res)
            except Exception:
                pass

    # Deduplicate by normalized title and DOI
    articles = []
    seen_keys = set()
    for art in raw_articles:
        title = art.get("title") or ""
        norm_title = re.sub(r"[^a-zA-Z0-9]", "", title.lower())
        doi = (art.get("doi") or "").lower().strip()

        if doi and doi in seen_keys:
            continue
        if norm_title and norm_title in seen_keys:
            continue

        if doi:
            seen_keys.add(doi)
        if norm_title:
            seen_keys.add(norm_title)

        # Calculate relevance rating
        rel = calculate_relevance_rating(query_text, title, art.get("abstract"))
        art["relevance"] = rel

        # Ensure abstract fallback text is clear
        if not art.get("abstract"):
            art["abstract"] = "Abstract unavailable from this source; full text not yet verified."

        articles.append(art)

    # Sort by relevance rating descending
    articles.sort(key=lambda x: x.get("relevance", {}).get("score_percent", 0), reverse=True)

    # Enrich top articles: Unpaywall direct OA PDF + scite.ai Smart Citations
    top_articles = articles[:8]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as enricher:
        pdf_futures = {}
        scite_futures = {}
        for idx, art in enumerate(top_articles):
            doi = art.get("doi")
            if doi and "10." in doi:
                if not art.get("open_access_pdf"):
                    pdf_futures[idx] = enricher.submit(resolve_unpaywall_pdf, doi)
                scite_futures[idx] = enricher.submit(resolve_scite_tallies, doi)

        for idx, fut in pdf_futures.items():
            try:
                oa_url = fut.result()
                if oa_url:
                    top_articles[idx]["open_access_pdf"] = oa_url
            except Exception:
                pass

        for idx, fut in scite_futures.items():
            try:
                scite_data = fut.result()
                if scite_data:
                    top_articles[idx]["smart_citations"] = scite_data
            except Exception:
                pass

    synthesis = generate_synthesis_matrix(top_articles)
    return {
        "query": query_text,
        "total_articles_retrieved": len(articles),
        "synthesis_matrix": synthesis["records"],
        "synthesis_table_markdown": synthesis["markdown_table"],
        "articles": top_articles
    }

# --- MASTER QUERY CONTROLLER ---
def query_all(compound_name=None, formula=None, elements=None):
    results = {
        "query_parameters": {
            "compound_name": compound_name,
            "formula": formula,
            "elements": elements
        },
        "chemical_substances": {},
        "materials_and_simulations": {},
        "thermodynamics_and_ionic_liquids": {},
        "research_literature_and_abstracts": {}
    }

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        chem_futures = {}
        mat_futures = {}
        thermo_futures = {}

        target_name = compound_name or formula
        if target_name:
            chem_futures["PubChem"] = executor.submit(query_pubchem, target_name)
            chem_futures["ChemSpider / RSC"] = executor.submit(query_chemspider, target_name)
            chem_futures["EPA CompTox (CTX)"] = executor.submit(query_comptox, target_name)
            kt = query_kamlet_taft(target_name)
            if kt:
                results["chemical_substances"]["Kamlet-Taft Solvatochromic"] = kt

        if compound_name:
            thermo_futures["ILThermo / NIST"] = executor.submit(query_ilthermo, compound_name)
            thermo_futures["NIST Chemistry WebBook"] = executor.submit(query_nist_webbook, compound_name)
            thermo_futures["CoolProp EOS"] = executor.submit(query_coolprop, compound_name)
            poly = query_polymer_specs(compound_name)
            if poly and poly.get("status") == "success":
                results["materials_and_simulations"]["Polymer Engineering Specs"] = poly

        if formula or elements:
            mat_futures["Materials Project"] = executor.submit(query_materials_project, formula, elements)
            mat_futures["OQMD (Northwestern)"] = executor.submit(query_oqmd, formula, elements)
            mat_futures["C2DB (2D Materials)"] = executor.submit(query_c2db, formula, elements)
            mat_futures["Duke AFLOW"] = executor.submit(query_aflow, elements, formula)
            mat_futures["COD (3D Crystals)"] = executor.submit(query_cod, elements, formula)
            mat_futures["NOMAD (Simulations)"] = executor.submit(query_nomad, formula, elements)

        target_mof = compound_name or formula
        if target_mof:
            mat_futures["CoRE MOF / MOFdb"] = executor.submit(query_mofdb, target_mof)

        lit_query = f"{compound_name or ''} {formula or ''}".strip()
        lit_future = executor.submit(query_research_literature, lit_query) if lit_query else None

        # Collect
        for k, fut in chem_futures.items():
            results["chemical_substances"][k] = fut.result()
        for k, fut in mat_futures.items():
            results["materials_and_simulations"][k] = fut.result()
        for k, fut in thermo_futures.items():
            res = fut.result()
            if k == "CoolProp EOS" and isinstance(res, dict) and res.get("status") == "error":
                continue  # Silently skip CoolProp if compound is not a fluid in its library
            results["thermodynamics_and_ionic_liquids"][k] = res
        if lit_future:
            results["research_literature_and_abstracts"] = lit_future.result()

    return results

def main():
    parser = argparse.ArgumentParser(description="Research-First Chemistry, Materials & Literature Discovery Hub")
    parser.add_argument("--compound", help="Compound or material name (e.g. 'EMIM TFSI', 'zylon', 'polybenzoxazole')")
    parser.add_argument("--formula", help="Chemical formula (e.g. 'SiO2', 'C6H6')")
    parser.add_argument("--elements", help="Comma-separated constituent elements (e.g. 'Si,O' or 'C,H,F,N,O,S')")
    parser.add_argument("--polymer-spec", help="Curated high-performance polymer specifications (e.g. 'zylon', 'pbo', 'kevlar', 'kapton', 'pvdf', 'ptfe', 'pegda', 'peek', 'nafion')")
    parser.add_argument("--coolprop", help="Fluid name for CoolProp thermodynamic & transport equations of state (e.g. 'Water', 'Ethanol', 'CO2')")
    parser.add_argument("--temp", type=float, default=298.15, help="Temperature in Kelvin for CoolProp or Walden calculation (default: 298.15 K)")
    parser.add_argument("--pressure", type=float, default=101325.0, help="Pressure in Pa for CoolProp (default: 101325 Pa)")
    parser.add_argument("--walden", action="store_true", help="Calculate Walden product, deviation (Delta W), ionicity (%%), and ion-pairing regime")
    parser.add_argument("--conductivity", type=float, help="Ionic conductivity in mS/cm for Walden calculation")
    parser.add_argument("--viscosity", type=float, help="Dynamic viscosity in mPa.s for Walden calculation")
    parser.add_argument("--density", type=float, help="Density in g/cm3 for Walden calculation (optional, for molar conductivity)")
    parser.add_argument("--mw", type=float, help="Molar mass in g/mol for Walden calculation (optional)")
    parser.add_argument("--kamlet-taft", help="Query Kamlet-Taft solvatochromic polarity parameters (alpha, beta, pi*)")
    parser.add_argument("--nist-webbook", help="Query NIST Chemistry WebBook for thermochemical and Antoine parameters")
    parser.add_argument("--aflow", action="store_true", help="Query Duke AFLOW for DFT elastic moduli and mechanical properties")
    parser.add_argument("--oqmd", help="Query Northwestern OQMD for DFT formation energies, stability, and crystal prototypes (e.g. 'Fe2O3')")
    parser.add_argument("--c2db", help="Query DTU C2DB via OPTIMADE for 2D monolayer materials (e.g. 'MoS2', 'graphene', 'BN')")
    parser.add_argument("--mofdb", help="Query Northwestern CoRE MOF / MOFdb for metal-organic frameworks, surface areas, and pore sizes (e.g. 'UiO-66', 'MOF-5')")
    parser.add_argument("--output", help="Save combined JSON report to file")
    parser.add_argument("--seed-doi", help="Explore citation graph / connected papers around a seed DOI or query")
    parser.add_argument("--graph-mode", choices=["related", "forward", "backward"], default="related", help="Citation graph mode: 'related' (co-citation / Connected Papers), 'forward' (citing works), 'backward' (seminal references)")
    parser.add_argument("--deep-read", help="DOI or open-access PDF URL to deep-read using PyMuPDF (extracts experimental recipes and materials properties)")
    parser.add_argument("--synthesis-table", action="store_true", help="Display the Elicit/SciSpace comparative synthesis matrix in Markdown format")
    parser.add_argument("--export-bibtex", help="Path to export bibliography in BibTeX format (.bib) for Zotero / Overleaf")
    parser.add_argument("--export-ris", help="Path to export bibliography in RIS format (.ris) for Zotero / Mendeley / EndNote")

    args = parser.parse_args()
    if not (
        args.compound or args.formula or args.elements or args.seed_doi or args.deep_read or
        args.polymer_spec or args.coolprop or args.walden or args.kamlet_taft or args.nist_webbook or args.aflow or
        args.oqmd or args.c2db or args.mofdb
    ):
        parser.error("Must provide at least one query flag (e.g. --compound, --formula, --oqmd, --c2db, --mofdb, --polymer-spec, --coolprop, --walden, --seed-doi).")

    if args.walden:
        combined = calculate_walden_ionicity(
            conductivity_mS_cm=args.conductivity,
            viscosity_mPa_s=args.viscosity,
            density_g_cm3=args.density,
            molar_mass=args.mw,
            temperature_K=args.temp
        )
    elif args.polymer_spec:
        combined = query_polymer_specs(args.polymer_spec)
    elif args.coolprop:
        combined = query_coolprop(args.coolprop, T_K=args.temp, P_Pa=args.pressure)
    elif args.kamlet_taft:
        combined = query_kamlet_taft(args.kamlet_taft)
    elif args.nist_webbook:
        combined = query_nist_webbook(name_or_formula=args.nist_webbook)
    elif args.aflow:
        combined = query_aflow(elements=args.elements, formula=args.formula)
    elif args.oqmd:
        combined = query_oqmd(formula=args.oqmd, elements=args.elements)
    elif args.c2db:
        combined = query_c2db(formula=args.c2db, elements=args.elements)
    elif args.mofdb:
        combined = query_mofdb(name=args.mofdb)
    elif args.deep_read:
        combined = deep_read_pdf(args.deep_read)
    elif args.seed_doi:
        combined = explore_citation_graph(args.seed_doi, mode=args.graph_mode)
    else:
        combined = query_all(compound_name=args.compound, formula=args.formula, elements=args.elements)

    # Handle reference management export for Zotero / Mendeley
    articles_to_export = []
    if isinstance(combined, dict):
        if "research_literature_and_abstracts" in combined:
            articles_to_export = combined["research_literature_and_abstracts"].get("articles", [])
        elif "connected_works" in combined:
            articles_to_export = combined.get("connected_works", [])

    if articles_to_export and (args.export_bibtex or args.export_ris):
        export_summary = export_zotero_references(articles_to_export, bib_path=args.export_bibtex, ris_path=args.export_ris)
        combined["zotero_export"] = export_summary
        if args.export_bibtex:
            print(f"Exported {export_summary['bibtex_count']} BibTeX citations to {args.export_bibtex}", file=sys.stderr)
        if args.export_ris:
            print(f"Exported {export_summary['ris_count']} RIS citations to {args.export_ris}", file=sys.stderr)

    # Handle synthesis table display
    if args.synthesis_table and isinstance(combined, dict):
        matrix_md = None
        if "research_literature_and_abstracts" in combined:
            matrix_md = combined["research_literature_and_abstracts"].get("synthesis_table_markdown")
        elif "connected_works" in combined:
            matrix_md = generate_synthesis_matrix(combined["connected_works"])["markdown_table"]

        if matrix_md:
            print("\n" + "="*80)
            print("                 COMPARATIVE SYNTHESIS MATRIX (ELICIT / SCISPACE)                 ")
            print("="*80 + "\n")
            print(matrix_md)
            print("\n" + "="*80 + "\n")

    out_str = json.dumps(combined, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out_str)
        print(f"Successfully generated research & literature report into {args.output}")
    elif not args.synthesis_table:
        print(out_str)

if __name__ == "__main__":
    main()
