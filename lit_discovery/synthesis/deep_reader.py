"""PyMuPDF in-memory full-text reading and methodology extractor."""
import re
import requests
from lit_discovery.core.unpaywall import resolve_unpaywall_pdf

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

HEADERS = {"User-Agent": "LitDiscovery/1.0"}

def extract_material_properties(text):
    """Extracts key experimental metrics and parameters from scientific text."""
    props = {}
    if not text:
        return props
    cond = re.findall(r'(\d+(?:\.\d+)?(?:\s*[x×*]\s*10[−\-]?\d+)?\s*(?:mS|S|μS|uS)\s*[/·\s\-]*cm(?:[\^−\-]?1)?)', text, re.IGNORECASE)
    if cond:
        props['ionic_conductivity'] = list(dict.fromkeys(cond[:3]))
    poly = re.findall(r'\b(PBO|Zylon|polybenzoxazole|Kevlar|PPTA|Kapton|polyimide|PVDF|polyvinylidene fluoride|PTFE|polytetrafluoroethylene|PEGDA|PEEK|PVA|chitosan|cellulose|Nafion)\b', text, re.IGNORECASE)
    if poly:
        props['polymer_matrix'] = list(dict.fromkeys([p.strip() for p in poly]))
    ils = re.findall(r'(\[?[EBMH]MIM\]?\[?[A-Za-z0-9_]+\]?|\[?PYR[0-9_]+\]?\[?[A-Za-z0-9_]+\]?|TFSI|FSI|BF4|PF6|DCA|IL|ionic liquid)', text, re.IGNORECASE)
    if ils:
        props['ionic_liquids'] = list(dict.fromkeys([i.strip() for i in ils[:3]]))
    therm = re.findall(r'(\d+(?:\.\d+)?\s*(?:°C|K|deg\s*C))', text)
    if therm:
        props['thermal_properties'] = list(dict.fromkeys(therm[:3]))
    mod = re.findall(r'(\d+(?:\.\d+)?\s*(?:GPa|MPa|kPa))', text)
    if mod:
        props['mechanical_modulus'] = list(dict.fromkeys(mod[:3]))
    stretch = re.findall(r'(\d+(?:\.\d+)?\s*%)', text)
    if stretch:
        props['stretchability'] = list(dict.fromkeys(stretch[:2]))
    return props

def extract_sections_from_text(full_text):
    """Segments full text into Methods, Results, and Conclusions."""
    sections = {"experimental_methods": None, "results_and_discussion": None, "conclusions": None}
    if not full_text:
        return sections
    m_exp = re.search(r'\b(?:materials?\s+and\s+methods?|experimental(?:\s+section)?|fabrication|synthesis)\b', full_text, re.IGNORECASE)
    m_res = re.search(r'\b(?:results?\s+and\s+discussion|discussion|characterization)\b', full_text, re.IGNORECASE)
    m_con = re.search(r'\b(?:conclusions?|summary)\b', full_text, re.IGNORECASE)
    if m_exp:
        end_idx = m_res.start() if (m_res and m_res.start() > m_exp.start()) else (m_con.start() if m_con else len(full_text))
        sections["experimental_methods"] = full_text[m_exp.start():end_idx].strip()[:6000]
    if m_res:
        end_idx = m_con.start() if (m_con and m_con.start() > m_res.start()) else len(full_text)
        sections["results_and_discussion"] = full_text[m_res.start():end_idx].strip()[:6000]
    if m_con:
        sections["conclusions"] = full_text[m_con.start():m_con.start() + 3000].strip()
    return sections

def deep_read_pdf(target_doi_or_url, max_pages=30):
    """Downloads and parses an open-access PDF in memory without writing to disk."""
    if fitz is None:
        return {"status": "error", "error": "PyMuPDF (fitz) is not installed."}
    pdf_url = target_doi_or_url
    # 1. Handle arXiv URLs and arXiv DOIs directly
    if "arxiv.org/abs/" in target_doi_or_url:
        pdf_url = target_doi_or_url.replace("arxiv.org/abs/", "arxiv.org/pdf/")
        if not pdf_url.endswith(".pdf"):
            pdf_url += ".pdf"
    elif "10.48550/arxiv." in target_doi_or_url.lower():
        m_ax = re.search(r'10\.48550/arxiv\.([0-9]{4}\.[0-9]{4,5}|[a-z\-]+/[0-9]{7})', target_doi_or_url, re.I)
        if m_ax:
            pdf_url = f"https://arxiv.org/pdf/{m_ax.group(1)}.pdf"
    elif "10." in target_doi_or_url and not target_doi_or_url.startswith("http"):
        pdf_url = resolve_unpaywall_pdf(target_doi_or_url)
        if not pdf_url:
            return {"status": "not_found", "message": f"No open-access PDF could be resolved for DOI: {target_doi_or_url}"}
    elif target_doi_or_url.startswith("https://doi.org/"):
        doi_clean = target_doi_or_url.replace("https://doi.org/", "")
        if "10.48550/arxiv." in doi_clean.lower():
            m_ax = re.search(r'10\.48550/arxiv\.([0-9]{4}\.[0-9]{4,5}|[a-z\-]+/[0-9]{7})', doi_clean, re.I)
            if m_ax:
                pdf_url = f"https://arxiv.org/pdf/{m_ax.group(1)}.pdf"
        else:
            pdf_url = resolve_unpaywall_pdf(doi_clean)
            if not pdf_url:
                return {"status": "not_found", "message": f"No open-access PDF could be resolved for DOI: {target_doi_or_url}"}
    try:
        r = requests.get(pdf_url, headers=HEADERS, timeout=25)
        if r.status_code != 200:
            return {"status": "error", "error": f"Failed to download PDF from {pdf_url} (HTTP {r.status_code})"}
        doc = fitz.open(stream=r.content, filetype="pdf")
        pages_to_read = min(len(doc), max_pages)
        full_text_pages = []
        for pno in range(pages_to_read):
            full_text_pages.append(doc[pno].get_text())
        full_text = "\n".join(full_text_pages)
        sections = extract_sections_from_text(full_text)
        extracted_properties = extract_material_properties(full_text)
        return {
            "status": "success",
            "pdf_url": pdf_url,
            "total_pages": len(doc),
            "pages_analyzed": pages_to_read,
            "character_count": len(full_text),
            "extracted_properties": extracted_properties,
            "sections": sections
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
