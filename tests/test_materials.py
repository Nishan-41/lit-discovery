"""Unit tests for the zero-authentication structural materials subsystem."""
import pytest
from unittest.mock import patch, MagicMock

from lit_discovery.materials.optimade import formula_to_hill, query_materials_project_optimade
from lit_discovery.materials.oqmd import query_oqmd
from lit_discovery.materials.c2db import query_c2db
from lit_discovery.materials.mofdb import query_mofdb
from lit_discovery.materials.dispatcher import query_all_materials


def test_formula_to_hill():
    # Alphabetical when no Carbon
    assert formula_to_hill("TiO2") == "O2Ti"
    assert formula_to_hill("NaCl") == "ClNa"
    assert formula_to_hill("Fe2O3") == "Fe2O3"
    assert formula_to_hill("H2O") == "H2O"
    
    # Carbon first, then Hydrogen, then alphabetical
    assert formula_to_hill("C6H6") == "C6H6"
    assert formula_to_hill("C2H5OH") == "C2H6O"
    assert formula_to_hill("CH3Cl") == "CH3Cl"
    assert formula_to_hill("") == ""
    assert formula_to_hill(None) is None


def test_materials_project_optimade_empty():
    res = query_materials_project_optimade()
    assert res.get("status") == "skipped"


def test_oqmd_empty():
    res = query_oqmd()
    assert res.get("status") == "skipped"


def test_c2db_empty():
    res = query_c2db()
    assert res.get("status") == "skipped"


def test_mofdb_empty():
    res = query_mofdb()
    assert res.get("status") == "skipped"


@patch("lit_discovery.materials.optimade.requests.get")
def test_materials_project_optimade_mock(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [
            {
                "id": "mp-123",
                "attributes": {
                    "chemical_formula_reduced": "MoS2",
                    "nsites": 3,
                    "elements": ["Mo", "S"],
                    "lattice_vectors": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                    "space_group_symbol_hermann_mauguin": "P6_3/mmc"
                }
            }
        ]
    }
    mock_get.return_value = mock_resp

    res = query_materials_project_optimade(formula="MoS2")
    assert res.get("status") == "success"
    assert len(res.get("materials", [])) == 1
    assert res["materials"][0]["material_id"] == "mp-123"


@patch("lit_discovery.materials.oqmd.requests.get")
def test_oqmd_mock(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [
            {
                "entry_id": 456,
                "name": "Fe2O3",
                "composition": "Fe2 O3",
                "prototype": "Corundum",
                "spacegroup": "R-3c",
                "volume": 102.5,
                "band_gap": 1.2,
                "delta_e": -1.63,
                "stability": 0.01,
                "unit_cell": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
            }
        ],
        "meta": {"total_count": 1}
    }
    mock_get.return_value = mock_resp

    res = query_oqmd(formula="Fe2O3")
    assert res.get("status") == "success"
    assert len(res.get("materials", [])) == 1
    assert res["materials"][0]["entry_id"] == 456
    assert res["materials"][0]["formation_energy_eV_atom"] == -1.63


@patch("lit_discovery.materials.c2db.requests.get")
def test_c2db_mock(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [
            {
                "id": 789,
                "attributes": {
                    "chemical_formula_reduced": "MoS2",
                    "dimension_types": [1, 1, 0],
                    "elements": ["Mo", "S"],
                    "nsites": 3,
                    "lattice_vectors": [[3.18, 0, 0], [-1.59, 2.75, 0], [0, 0, 18.1]]
                }
            }
        ]
    }
    mock_get.return_value = mock_resp

    res = query_c2db(formula="MoS2")
    assert res.get("status") == "success"
    assert len(res.get("materials", [])) == 1
    assert res["materials"][0]["dimension_types"] == [1, 1, 0]


@patch("lit_discovery.materials.mofdb.requests.get")
def test_mofdb_mock(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [
            {
                "id": 999,
                "name": "UiO-66",
                "mofid": "Zr_MOF",
                "surface_area_m2g": 1200.0,
                "surface_area_m2cm3": 1400.0,
                "void_fraction": 0.55,
                "lcd": 11.5,
                "pld": 6.0,
                "database": "CoREMOF 2019",
                "cif": "data_cif..."
            }
        ]
    }
    mock_get.return_value = mock_resp

    res = query_mofdb(name="UiO-66")
    assert res.get("status") == "success"
    assert len(res.get("mofs", [])) == 1
    assert res["mofs"][0]["surface_area_m2g"] == 1200.0
    assert res["mofs"][0]["cif_available"] is True


@patch("lit_discovery.materials.dispatcher.query_mofdb")
@patch("lit_discovery.materials.dispatcher.query_c2db")
@patch("lit_discovery.materials.dispatcher.query_oqmd")
@patch("lit_discovery.materials.dispatcher.query_materials_project_optimade")
def test_query_all_materials_structure(mock_mp, mock_oqmd, mock_c2db, mock_mof):
    mock_mp.return_value = {"status": "success", "materials": []}
    mock_oqmd.return_value = {"status": "success", "materials": []}
    mock_c2db.return_value = {"status": "success", "materials": []}
    mock_mof.return_value = {"status": "success", "mofs": []}

    res = query_all_materials(formula="MoS2", limit=1)
    assert "query" in res
    assert "databases" in res
    dbs = res["databases"]
    assert "materials_project_optimade" in dbs
    assert "oqmd" in dbs
    assert "c2db_2d_materials" in dbs
    assert "core_mofdb" in dbs
