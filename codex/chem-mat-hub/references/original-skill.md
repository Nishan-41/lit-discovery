---
name: chem-mat-hub
description: >
  Unified multi-database platform for Chemical Engineering, Materials Science, Physical Chemistry,
  High-Performance Polymers, Ionic Liquids, and Multi-Source Literature. Dispatches concurrent parallel
  queries across PubChem (PUG-View & GHS), Duke AFLOW (AFLUX elastic moduli), Materials Project, NOMAD,
  COD Crystallography, ILThermo, NIST Chemistry WebBook, CoolProp Equations of State (120+ fluids),
  Walden Plot & Ionicity Calculator, Kamlet-Taft Solvatochromic Parameters, Polymer Engineering Specs
  (Zylon/PBO, Kevlar, Kapton, PVDF, PTFE, PEGDA, PEEK, Nafion), and 12 literature discovery engines
  (Semantic Scholar, Scopus, OpenAlex, Europe PMC, arXiv, OSTI.gov, CORE, DOAJ, DataCite, PubMed, Zenodo,
  Crossref) with scite.ai Smart Citations, Connected Papers citation graph exploration, and Unpaywall PDF resolving.
---

# Unified Chemistry, Materials & Engineering Research Hub

Query open physical science databases, materials simulation repositories, polymer engineering specifications, thermodynamic equations of state, and academic literature engines at once with a single command or Python function.

## Supported Capabilities & Integrated Databases:

### 1. Materials Science, Crystals & Mechanical Properties:
- **OQMD (Open Quantum Materials Database - Northwestern University)**: 1,000,000+ DFT-calculated inorganic structures, formation energies ($\Delta H_f$), thermodynamic stability (distance to convex hull), crystal prototypes, space groups, and unit cells (*Zero-Authentication*).
- **C2DB (Computational 2D Materials Database - DTU)**: Standardized OPTIMADE v1 queries for 2D monolayer structures, dimension types `[1, 1, 0]`, lattice vectors, and stoichiometry (*Zero-Authentication*).
- **CoRE MOF / MOFdb (Northwestern University)**: Porous crystalline frameworks, volumetric & gravimetric surface areas ($m^2/g$, $m^2/cm^3$), pore limiting diameter (PLD), largest cavity diameter (LCD), void fraction, and CIF downloads (*Zero-Authentication*).
- **Materials Project**: DFT electronic structures, band gaps, formation energies, stability convex hull (uses `MP_API_KEY`, with automatic fallback to zero-auth OPTIMADE v1 when unauthenticated).
- **Duke AFLOW (AFLUX API)**: DFT-calculated elastic moduli (Voigt, Reuss, VRH bulk & shear modulus, Poisson ratio, Debye temperature), band gaps, and formation enthalpies (*Zero-Authentication*).
- **High-Performance Polymer Engineering Specs**: Curated engineering specifications for **Zylon (PBO)**, **Kevlar (PPTA)**, **Kapton (PI)**, **PVDF**, **PTFE**, **PEGDA**, **PEEK**, and **Nafion** (tensile strength, tensile modulus, elongation, $T_g$, $T_m$, $T_d$, LOI %, dielectric constant, solvent resistance, dissolution/spinning superacids, and role in ionogels/electrolytes).
- **COD (Crystallography Open Database)**: 3D crystal structures, space groups, cell parameters, CIF downloads (*Zero-Authentication*).
- **NOMAD (Novel Materials Discovery)**: DFT, VASP, and MD computational simulations and trajectories (*Zero-Authentication*).

### 2. Physical Chemistry, Thermophysical EOS & Ionic Liquids:
- **CoolProp Equations of State**: High-precision thermophysical, thermodynamic, and transport properties (density, dynamic viscosity, thermal conductivity, isobaric heat capacity $C_p$, enthalpy, entropy, speed of sound, phase identification) for 120+ pure fluids and mixtures across arbitrary $(T, P)$ states.
- **NIST Chemistry WebBook**: Standard enthalpy of formation ($\Delta_f H^\circ$), combustion enthalpy ($\Delta_c H^\circ$), boiling/melting points, heat capacities, and **Antoine equation vapor pressure parameters** ($A, B, C$).
- **Walden Plot & Ionicity Calculator**: Electrolyte molar conductivity $\Lambda = \frac{\kappa_{mS/cm} \times M}{1000 \times \rho_{g/cm^3}}$, Walden product $W = \Lambda \cdot \eta$, deviation $\Delta W = \log_{10} \Lambda - \log_{10}(1/\eta)$ relative to the ideal aqueous KCl line, percentage ionicity ($10^{\Delta W} \times 100\%$), and dissociation regime classification.
- **Kamlet-Taft Solvatochromic Polarity Parameters**: Hydrogen-bond donating acidity ($\alpha$), hydrogen-bond accepting basicity ($\beta$), and dipolarity/polarizability ($\pi^*$) for ionic liquids and polymer processing solvents.
- **ILThermo (IUPAC/NIST)**: Experimental ionic liquid transport & thermophysical properties (viscosity, conductivity, density, phase equilibria).

### 3. Chemical Substances & Safety:
- **PubChem & PUG-View**: Chemical identifiers, canonical SMILES, MW, IUPAC name, experimental physical properties (boiling point, melting point, density, vapor pressure, flash point, viscosity), and official **GHS hazard statements and signal words**.
- **ChemSpider / RSC**: Royal Society of Chemistry curated chemical records (uses `RSC_API_KEY`).
- **EPA CompTox (CTX)**: Curated substance IDs, CASRN, preferred chemical names (uses `CTX_API_KEY`).

### 4. Multi-Source Literature Discovery & Smart Citations (Concurrent Retrieval):
- **Semantic Scholar (S2AG)**: Academic graph search with AI TL;DR summaries, citation intent, and open-access PDFs (uses `S2_API_KEY`).
- **Europe PMC (EMBL-EBI)**: >43M biomedical & biomaterials records, structured XML abstracts, and PMCID links.
- **arXiv API**: Preprints in materials science (`cond-mat.mtrl-sci`), polymer physics (`cond-mat.soft`), and chemical physics.
- **OSTI.gov (DOE)**: U.S. Department of Energy national lab research reports, battery/electrolyte, and energy materials papers.
- **CORE (Repositories)**: >260M research outputs from global university & institutional repositories with direct PDF links (uses `CORE_API_KEY`).
- **DOAJ (Directory of Open Access Journals)**: 20,000+ peer-reviewed open access journals with full abstracts.
- **DataCite**: Doctoral dissertations, academic theses, preprints, and open experimental datasets.
- **PubMed (NLM)**: National Library of Medicine biomedical and biochemical citations.
- **Zenodo (CERN / OpenAIRE)**: Global open-science repository for preprints, datasets, theses, and open-access publications with direct PDF downloads.
- **Elsevier Scopus**: Peer-reviewed abstract retrieval via official Elsevier API (uses `SCOPUS_API_KEY`).
- **OpenAlex**: Global scientific graph, inverted-index abstract reconstruction.
- **Crossref**: Official DOI publisher metadata and XML abstract parsing.
- **scite.ai Smart Citations**: Automated empirical consensus tallies (Supporting, Contrasting, Mentioning citations).
- **Unpaywall**: Automated direct legal PDF resolver for all retrieved DOIs.

---

## Citation Graph & Connected Papers (Snowballing Discovery)
- **`related` (Connected Papers style)**: Co-cited and bibliographically coupled works that tackle the same research problem.
- **`forward` (Derivative Works)**: Newer studies directly citing the seed paper.
- **`backward` (Foundational Works)**: Seminal references cited by the seed paper.

---

## Advanced Synthesis & Extraction Features

### 1. Comparative Synthesis Matrix (Elicit / SciSpace Style)
Extract structured comparative tables across papers (Host Polymer, Ionic Liquid, Ionic Conductivity $\sigma$, Degradation Temp $T_d$, Mechanical Modulus, and scite.ai Consensus):
```bash
python scripts/unified_chem_mat_hub.py --compound "ionogel" --synthesis-table
```

### 2. Full-Text Deep Reading via PyMuPDF (fitz)
Download and parse open-access PDFs in-memory, extracting experimental procedures, materials parameters, and characterization sections:
```bash
python scripts/unified_chem_mat_hub.py --deep-read "10.1038/s41586-021-03819-2"
```

### 3. Zotero & Reference Management Export (BibTeX / RIS)
Export all discovered citations into Zotero/Mendeley/Overleaf format via official DOI content negotiation:
```bash
python scripts/unified_chem_mat_hub.py --compound "zylon ionogel" --export-bibtex zylon_papers.bib --export-ris zylon_papers.ris
```

---

## Command Line Quick Reference

### Materials, Crystals & 2D Structures:
```bash
# Query curated engineering specifications for Zylon (PBO)
python scripts/unified_chem_mat_hub.py --polymer-spec "zylon"

# Query Northwestern OQMD for DFT formation energies, stability, and prototypes (Zero-Auth)
python scripts/unified_chem_mat_hub.py --oqmd "Fe2O3"

# Query DTU C2DB for 2D monolayer structures and lattice vectors via OPTIMADE (Zero-Auth)
python scripts/unified_chem_mat_hub.py --c2db "MoS2"

# Query Northwestern CoRE MOF / MOFdb for surface area and pore diameter (Zero-Auth)
python scripts/unified_chem_mat_hub.py --mofdb "UiO-66"

# Query Duke AFLOW for DFT elastic moduli of titanium oxides (Zero-Auth)
python scripts/unified_chem_mat_hub.py --aflow --elements "Ti,O"
```

### Physical Chemistry & Equations of State:
```bash
# Calculate CoolProp thermophysical properties (Water at 25 °C, 1 atm)
python scripts/unified_chem_mat_hub.py --coolprop "Water" --temp 298.15 --pressure 101325

# Supercritical CO2 state properties (310 K, 80 bar)
python scripts/unified_chem_mat_hub.py --coolprop "CO2" --temp 310.0 --pressure 8000000

# NIST Chemistry WebBook thermochemical & Antoine vapor pressure parameters
python scripts/unified_chem_mat_hub.py --nist-webbook "benzene"

# Walden plot & ionicity calculation for [EMIM][TFSI]
python scripts/unified_chem_mat_hub.py --walden --conductivity 9.1 --viscosity 32.0 --density 1.52 --mw 391.31

# Query Kamlet-Taft solvatochromic polarity parameters
python scripts/unified_chem_mat_hub.py --kamlet-taft "[EMIM][TFSI]"
```

### Master Hub Query:
```bash
# Query all chemical, thermodynamic, polymer, and literature engines simultaneously
python scripts/unified_chem_mat_hub.py --compound "polybenzoxazole" --output pbo_full_report.json
```
