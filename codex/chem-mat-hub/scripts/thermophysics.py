"""Identity-checked ILThermo retrieval; raw data and review state stay separate."""
import html
import math
import re
from collections import Counter, defaultdict

import requests

ROOT = 'https://ilthermo.boulder.nist.gov/ILT2/'
CONFIG = {'max_sets': 50, 'compound_id': None, 'formula': None}
ALIASES = {
    'emimtfsi': ('ABXNou', 'C8H11F6N3O4S2', '1-ethyl-3-methylimidazolium bis((trifluoromethyl)sulfonyl)imide'),
    'emimntf2': ('ABXNou', 'C8H11F6N3O4S2', '1-ethyl-3-methylimidazolium bis((trifluoromethyl)sulfonyl)imide'),
    'emimtf2n': ('ABXNou', 'C8H11F6N3O4S2', '1-ethyl-3-methylimidazolium bis((trifluoromethyl)sulfonyl)imide'),
    '174899822': ('ABXNou', 'C8H11F6N3O4S2', '1-ethyl-3-methylimidazolium bis((trifluoromethyl)sulfonyl)imide'),
    'emimdca': ('AAiEeh', 'C8H11N5', '1-ethyl-3-methylimidazolium dicyanamide'),
    '370865897': ('AAiEeh', 'C8H11N5', '1-ethyl-3-methylimidazolium dicyanamide'),
}
for _identity in list(ALIASES.values()):
    ALIASES[re.sub('[^a-z0-9]', '', _identity[2].casefold())] = _identity


def plain(value):
    return html.unescape(re.sub('<[^>]+>', '', str(value)))


def normalized(value):
    return re.sub('[^a-z0-9]', '', plain(value).casefold())


def evidence_record(evidence_type, *, source, page=None, locator=None, method=None,
                    inputs=None, verification_note=None):
    """Explicit promotion only; extraction never implies scientific verification."""
    allowed = {'database_value', 'metadata_candidate', 'pdf_extraction_candidate',
               'verified_paper_table', 'calculation', 'unresolved_conflict'}
    if evidence_type not in allowed:
        raise ValueError('Unknown evidence type')
    if not source:
        raise ValueError('Evidence requires source provenance')
    if evidence_type == 'verified_paper_table' and not (page and locator and verification_note):
        raise ValueError('Verified paper table requires page, locator and verification note')
    if evidence_type == 'calculation' and not (method and inputs):
        raise ValueError('Calculation requires method and source inputs')
    return {'evidence_type': evidence_type, 'source': source, 'page': page,
            'locator': locator, 'method': method, 'inputs': inputs,
            'verification_note': verification_note,
            'scientific_review_status': 'verified' if evidence_type == 'verified_paper_table' else 'not_reviewed'}


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coordinates(dataset, row):
    coords = {}
    for head, cell in zip(dataset.get('dhead', [])[:-1], row[:-1]):
        coords[plain(head[0])] = cell[0] if cell else None
    coords['constraints'] = str(dataset.get('constr', []))
    return tuple(sorted(coords.items()))


def assess(datasets):
    """Flag suspicious values without rewriting values/units or choosing a winner."""
    groups = defaultdict(list)
    cp_by_ref = defaultdict(list)
    for entry in datasets:
        data = entry.get('data', {})
        entry['quality_flags'] = []
        if not data.get('dhead'):
            entry['quality_flags'].append({'code': 'missing_table_headers'})
            continue
        prop = plain(data['dhead'][-1][0])
        phase = str(data.get('phases', []))
        ref = data.get('ref', {}).get('full', '')
        if 'Heat capacity at constant pressure' in prop:
            cp_by_ref[ref].append((phase, data))
        for index, row in enumerate(data.get('data', [])):
            if len(row) != len(data['dhead']) or not row or not row[-1]:
                entry['quality_flags'].append({'code': 'malformed_row', 'row': index + 1})
                continue
            value = _number(row[-1][0])
            if value is None or not math.isfinite(value):
                entry['quality_flags'].append({'code': 'nonnumeric_or_nonfinite', 'row': index + 1})
                continue
            if value <= 0 and any(p in prop.lower() for p in ('density', 'heat capacity', 'viscosity', 'thermal conductivity')):
                entry['quality_flags'].append({'code': 'nonpositive_physical_quantity', 'row': index + 1})
            groups[(prop, phase, _coordinates(data, row))].append((entry, value, index + 1, ref))
    # Compare matching units, phase, temperature and pressure only, across references.
    for values in groups.values():
        positive = [v for _, v, _, _ in values if v > 0]
        if len({r for _, _, _, r in values}) < 2 or not positive or max(positive)/min(positive) <= 1.10:
            continue
        for entry, _, row, _ in values:
            entry['quality_flags'].append({'code': 'unresolved_source_conflict', 'row': row,
                'note': 'More than 10% difference at matching recorded conditions; samples/methods may differ. Not an uncertainty test.'})
    for entry in datasets:
        data = entry.get('data', {})
        heads = data.get('dhead', [])
        if not heads or not plain(heads[-1][0]).startswith('Enthalpy') or 'kJ/mol' not in plain(heads[-1][0]):
            continue
        ti = next((i for i, h in enumerate(heads[:-1]) if plain(h[0]) == 'Temperature, K'), None)
        if ti is None:
            continue
        # Match all non-temperature conditions before taking a finite difference.
        slices = defaultdict(list)
        for row in data.get('data', []):
            if len(row) != len(heads):
                continue
            t, h = _number(row[ti][0]), _number(row[-1][0])
            if t is not None and h is not None:
                slices[tuple(str(c) for i,c in enumerate(row[:-1]) if i != ti)].append((t,h))
        for other_conditions, points in slices.items():
            points.sort()
            for (t1,h1),(t2,h2) in zip(points, points[1:]):
                if t2 <= t1:
                    continue
                slope = 1000 * (h2-h1)/(t2-t1)
                for phase, cp in cp_by_ref[data.get('ref',{}).get('full','')]:
                    if phase != str(data.get('phases',[])):
                        continue
                    if 'J/K/mol' not in plain(cp['dhead'][-1][0]):
                        continue
                    # Require shared reference and an actual Cp temperature in interval.
                    cti = next((i for i,h in enumerate(cp['dhead'][:-1]) if plain(h[0]) == 'Temperature, K'), None)
                    if cti is None:
                        continue
                    if data.get('constr',[]) != cp.get('constr',[]):
                        continue
                    if [plain(h[0]) for i,h in enumerate(heads[:-1]) if i!=ti] != [plain(h[0]) for i,h in enumerate(cp['dhead'][:-1]) if i!=cti]:
                        continue
                    vals = [_number(r[-1][0]) for r in cp.get('data',[]) if _number(r[cti][0]) is not None
                            and t1 <= float(r[cti][0]) <= t2
                            and tuple(str(c) for i,c in enumerate(r[:-1]) if i!=cti)==other_conditions]
                    if any(v and v > 0 and 300 < slope/v < 3000 for v in vals):
                        flag={'code':'enthalpy_cp_unit_inconsistency','note':'dH/dT in declared kJ/mol differs from same-source Cp by about 1000x. Verify original table; raw values unchanged.'}
                        if flag not in entry['quality_flags']:entry['quality_flags'].append(flag)
    for entry in datasets:
        if any(f['code']=='unresolved_source_conflict' for f in entry['quality_flags']):
            entry['evidence']['interpretation_status'] = 'unresolved_conflict'
    return datasets


def query(compound_name, *, max_sets=None, compound_id=None, formula=None):
    cap = CONFIG['max_sets'] if max_sets is None else max_sets
    if not isinstance(cap,int) or cap < 0:
        raise ValueError('ILThermo max_sets must be nonnegative; 0 means all')
    alias = ALIASES.get(normalized(compound_name))
    lookup = alias[2] if alias else compound_name
    expected_id = compound_id or CONFIG['compound_id']
    expected_formula = formula or CONFIG['formula'] or (alias[1] if alias else None)
    if alias:
        expected_id = expected_id or alias[0]
    response = requests.get(ROOT+'ilsearch', params={'cmp':lookup,'nc':1}, timeout=30)
    response.raise_for_status()
    index = response.json()
    if not isinstance(index.get('res'),list):
        return {'status':'schema_error','datasets':[], 'message':'ILThermo search response has no dataset list'}
    candidates = {}
    rows = []
    for row in index['res']:
        if not isinstance(row,list) or len(row)<9:
            continue
        if row[5] is not None or row[6] is not None:
            continue
        candidates[row[4]] = row[8]
        if expected_id and row[4] != expected_id:
            continue
        if not expected_id and normalized(row[8]) != normalized(lookup):
            continue
        rows.append(row)
    ids = {r[4] for r in rows}
    if len(ids)!=1:
        return {'status':'identity_unresolved','query':compound_name,'datasets':[],
                'candidates':[{'compound_id':k,'name':v} for k,v in candidates.items()],
                'message':'No unique exact single-component identity. Supply --ilthermo-compound-id; no approximate match accepted.'}
    resolved_id = next(iter(ids))
    expected_name = candidates[resolved_id]
    selected = rows[:cap] if cap else rows
    datasets=[];excluded=[];failures=[]
    for row in selected:
        sid=row[0]
        try:
            r=requests.get(ROOT+'ilset',params={'set':sid},timeout=30);r.raise_for_status();data=r.json()
            components=data.get('components',[])
            component=components[0] if len(components)==1 else {}
            if (component.get('idout') != resolved_id or normalized(component.get('name','')) != normalized(expected_name)
                or (expected_formula and plain(component.get('formula','')) != expected_formula)):
                excluded.append({'set_id':sid,'reason':'dataset_identity_or_formula_mismatch'});continue
            if not isinstance(data.get('data'),list) or not isinstance(data.get('dhead'),list):
                failures.append({'set_id':sid,'status':'schema_error'});continue
            actual_formula = plain(component.get('formula',''))
            if not actual_formula:
                excluded.append({'set_id':sid,'reason':'missing_molecular_formula'});continue
            expected_formula = expected_formula or actual_formula
            datasets.append({'set_id':sid,'citation':row[1],'property':row[2],'phase':row[3],
                'compound_id':resolved_id,'source_url':ROOT+'ilset?set='+sid,'data':data,
                'evidence':evidence_record('database_value',source=ROOT+'ilset?set='+sid)})
        except requests.RequestException as exc:
            failures.append({'set_id':sid,'status':'request_failed','error_type':type(exc).__name__})
        except (ValueError,TypeError,KeyError):
            failures.append({'set_id':sid,'status':'schema_error'})
    assess(datasets)
    truncated=len(selected)<len(rows)
    return {'status':'partial' if truncated or failures or excluded else 'success', 'query':compound_name,
        'identity':{'compound_id':resolved_id,'name':expected_name,'formula':expected_formula,
                    'verified_in_each_dataset':True},
        'total_sets':len(rows),'sets_retrieved':len(datasets),'truncated':truncated,
        'coverage':{'scope':'returned exact-identity single-component index; multiple phases',
                    'returned_search_rows':len(index['res']),'max_sets':cap,'not_exhaustive_literature':True},
        'datasets':datasets,'excluded':excluded,'failures':failures,
        'quality_summary':dict(Counter(f['code'] for d in datasets for f in d['quality_flags'])),
        'review_status':'database_values_not_scientifically_reviewed'}
