import copy
import json
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import codex_hub as runtime
import research
import thermophysics as tp
from scopus_query import expression


def response(data,status=200):
    r=requests.Response();r.status_code=status;r._content=json.dumps(data).encode();return r


@pytest.fixture(autouse=True)
def isolate(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime.TRANSPORT,'no_cache',True)
    monkeypatch.setattr(runtime.TRANSPORT,'retries',0)
    monkeypatch.setattr(runtime.TRANSPORT,'cache_path',tmp_path/'cache.db')
    monkeypatch.setattr(research.time,'sleep',lambda _:None)
    monkeypatch.setattr(runtime.TRANSPORT,'request',lambda *a,**k:pytest.fail('Unexpected network call'))
    monkeypatch.setitem(tp.CONFIG,'max_sets',50)
    monkeypatch.setitem(tp.CONFIG,'compound_id',None)
    monkeypatch.setitem(tp.CONFIG,'formula',None)
    research.STATE.pager=None


def table(prop='Heat capacity at constant pressure, J/K/mol',rows=None,**kw):
    d={'components':[{'idout':'AAiEeh','name':'1-ethyl-3-methylimidazolium dicyanamide','formula':'C8H11N5'}],
       'dhead':[['Temperature, K',None],['Pressure, kPa',None],[prop,'Liquid']],
       'data':rows or [[['298.15'],['101.325'],['315','1']]],'phases':['Liquid'],
       'ref':{'full':'Author 2026'},'constr':[]}
    d.update(kw);return d


def entry(data):
    return {'data':data,'evidence':tp.evidence_record('database_value',source='NIST')}


def index(n=7):
    return {'res':[[str(i),'Author','Heat capacity','Liquid','AAiEeh',None,None,1,'1-ethyl-3-methylimidazolium dicyanamide'] for i in range(n)]}


def install_index(monkeypatch,idx,details=None):
    calls=[]
    def fake(session,method,url,**kw):
        calls.append((url,kw.get('params')))
        return response(idx if url.endswith('ilsearch') else (details or table()))
    monkeypatch.setattr(runtime.TRANSPORT,'request',fake)
    return calls


def test_all_datasets_not_five_preview(monkeypatch):
    calls=install_index(monkeypatch,index())
    r=tp.query('[EMIM][DCA]',max_sets=0)
    assert len(r['datasets'])==7 and r['status']=='success'
    assert len(calls)==8
    assert r['datasets'][0]['data']['data'][0][-1]==['315','1']
    assert r['datasets'][0]['evidence']['scientific_review_status']=='not_reviewed'


def test_explicit_limit_is_partial(monkeypatch):
    install_index(monkeypatch,index())
    r=tp.query('EMIM DCA',max_sets=2)
    assert r['truncated'] and r['status']=='partial' and r['total_sets']==7


def test_reject_substring_and_mixture(monkeypatch):
    idx=index(1)
    idx['res'] += [['wrong','Author','Cp','Liquid','other',None,None,1,'2-ethyl-1-ethyl-3-methylimidazolium dicyanamide'],
                   ['mix','Author','Cp','Liquid','AAiEeh','water',None,1,'1-ethyl-3-methylimidazolium dicyanamide']]
    calls=install_index(monkeypatch,idx)
    r=tp.query('EMIM DCA',max_sets=0)
    assert r['sets_retrieved']==1 and len(calls)==2


@pytest.mark.parametrize('field,value',[('idout','wrong'),('name','substituted salt'),('formula','C9H13N5')])
def test_recheck_downloaded_identity(monkeypatch,field,value):
    data=table();data['components'][0][field]=value
    install_index(monkeypatch,index(1),data)
    r=tp.query('EMIM DCA')
    assert not r['datasets'] and len(r['excluded'])==1 and r['status']=='partial'


def test_ambiguous_identity_not_guessed(monkeypatch):
    install_index(monkeypatch,index())
    r=tp.query('imidazolium')
    assert r['status']=='identity_unresolved' and not r['datasets']


def test_failed_set_is_not_zero_matches(monkeypatch):
    def fake(s,m,u,**kw):return response(index(1)) if u.endswith('ilsearch') else response({},503)
    monkeypatch.setattr(runtime.TRANSPORT,'request',fake)
    r=tp.query('EMIM DCA')
    assert r['status']=='partial' and r['failures'][0]['status']=='request_failed'


def test_schema_error(monkeypatch):
    install_index(monkeypatch,{'message':'not data'})
    assert tp.query('EMIM DCA')['status']=='schema_error'


def test_unit_check_preserves_raw():
    h=table('Enthalpy, kJ/mol',[[['290'],['101.325'],['94860','380']],[['298.15'],['101.325'],['98960','400']]])
    cp=table(rows=[[['298.15'],['101.325'],['505.7','1.4']]])
    raw=copy.deepcopy(h)
    values=tp.assess([entry(h),entry(cp)])
    assert any(f['code']=='enthalpy_cp_unit_inconsistency' for f in values[0]['quality_flags'])
    assert values[0]['data']==raw


def test_correct_enthalpy_not_flagged():
    h=table('Enthalpy, kJ/mol',[[['290'],['101.325'],['94.86']],[['298.15'],['101.325'],['98.96']]])
    assert not tp.assess([entry(h),entry(table(rows=[[['298.15'],['101.325'],['505.7']]]))])[0]['quality_flags']


def test_cp_different_pressure_not_compared():
    h=table('Enthalpy, kJ/mol',[[['290'],['101.325'],['94860']],[['298.15'],['101.325'],['98960']]])
    cp=table(rows=[[['298.15'],['5000'],['505.7']]])
    assert not tp.assess([entry(h),entry(cp)])[0]['quality_flags']


@pytest.mark.parametrize('value',['nan','inf','-1'])
def test_invalid_values_flagged_without_replacement(value):
    raw=table(rows=[[['298.15'],['101.325'],[value]]])
    r=tp.assess([entry(raw)])[0]
    assert r['quality_flags'] and r['data']['data'][0][-1][0]==value


def test_conflict_requires_matching_conditions_and_units():
    a=entry(table('Specific density, kg/m3',rows=[[['298.15'],['101.325'],['1000']]]))
    b=entry(table('Specific density, kg/m3',rows=[[['298.15'],['101.325'],['1300']]],ref={'full':'Other'}))
    values=tp.assess([a,b])
    assert values[0]['evidence']['interpretation_status']=='unresolved_conflict'
    b['data']['data'][0][0]=['303.15']
    assert not tp.assess([a,b])[0]['quality_flags']


def test_verification_and_calculation_require_evidence():
    with pytest.raises(ValueError):tp.evidence_record('verified_paper_table',source='paper')
    with pytest.raises(ValueError):tp.evidence_record('calculation',source='paper')
    r=tp.evidence_record('verified_paper_table',source='DOI',page=2,locator='Table 1',verification_note='Visual check')
    assert r['scientific_review_status']=='verified'
    assert tp.evidence_record('calculation',source='DOI',method='M/rho',inputs={'M':177,'rho':1.1})['evidence_type']=='calculation'


def test_extraction_never_auto_verifies():
    r=research.evidence('Young modulus 20 MPa',source='pdf',page=2)
    assert r and all(x['evidence_type']=='pdf_extraction_candidate' and x['scientific_review_status']=='not_reviewed' for x in r)


def test_scopus_chemical_punctuation_literal():
    q=expression('TITLE-ABS-KEY(1-ethyl-3-methylimidazolium bis(trifluoromethylsulfonyl)imide heat capacity)')
    assert '"bis(trifluoromethylsulfonyl)imide"' in q and ' AND heat AND capacity' in q


def test_scopus_400_fallback_and_safe_diagnostics(monkeypatch):
    calls=[]
    def fake(session,method,url,**kw):
        calls.append(kw['params']['query'])
        return response({'service-error':{'status':{'statusCode':'INVALID_INPUT','statusText':'secret'}}},400) if len(calls)==1 else response({'search-results':{'entry':[]}})
    monkeypatch.setattr(runtime.TRANSPORT,'request',fake)
    runtime.LOCAL.trace=[]
    result=requests.get('https://api.elsevier.com/content/search/scopus',params={'query':'TITLE-ABS-KEY(bis(foo)imide)'})
    trace=runtime.LOCAL.trace;runtime.LOCAL.trace=None
    assert result.status_code==200 and len(calls)==2 and calls[0]!=calls[1]
    assert trace[-1]['initial_http_status']==400 and trace[-1]['api_error_code']=='INVALID_INPUT'
    assert 'secret' not in str(trace)


@pytest.mark.parametrize('status',[401,403,429])
def test_no_query_fallback_for_auth_or_rate_limit(monkeypatch,status):
    calls=[]
    def fake(*a,**k):calls.append(k);return response({},status)
    monkeypatch.setattr(runtime.TRANSPORT,'request',fake)
    requests.get('https://api.elsevier.com/content/search/scopus',params={'query':'bis(foo)'})
    assert len(calls)==1
