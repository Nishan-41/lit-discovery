"""Zero-Authentication Structural Materials Discovery Subsystem.

Provides open, zero-auth queries across:
- OQMD (Open Quantum Materials Database - Northwestern)
- C2DB (Computational 2D Materials Database - DTU)
- CoRE MOF / MOFdb (Northwestern University)
- Materials Project via standardized OPTIMADE v1 protocol
"""

from lit_discovery.materials.optimade import query_materials_project_optimade, formula_to_hill
from lit_discovery.materials.oqmd import query_oqmd
from lit_discovery.materials.c2db import query_c2db
from lit_discovery.materials.mofdb import query_mofdb
from lit_discovery.materials.dispatcher import query_all_materials

__all__ = [
    "query_materials_project_optimade",
    "formula_to_hill",
    "query_oqmd",
    "query_c2db",
    "query_mofdb",
    "query_all_materials",
]
