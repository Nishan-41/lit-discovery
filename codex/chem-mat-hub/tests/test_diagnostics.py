import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from diagnostics import summarize
import codex_hub as runtime


def test_success_failure_cache_and_untested_are_distinct():
    result={'source_diagnostics':[
        {'source':'openalex','status':'returned_data','records':2,'requests':[{'host':'api.openalex.org','cache':'hit','attempts':0,'http_status':200}]},
        {'source':'scopus','status':'request_failed','records':0,'requests':[{'host':'api.elsevier.com','http_status':400,'attempts':1,'error_message':'secret','url':'https://bad/?token=secret'}]}]}
    r=summarize(result,['openalex','scopus','pubchem'],requested=('openalex','scopus'))
    sources={s['source']:s for s in r['sources']}
    assert sources['openalex']['state']=='successful' and sources['openalex']['cache_state']=='all_hits'
    assert not sources['openalex']['network_tested']
    assert sources['scopus']['state']=='failed' and sources['scopus']['network_tested']
    assert sources['pubchem']['state']=='untested' and sources['pubchem']['untested_reason']=='not_requested'
    assert 'secret' not in json.dumps(r) and 'token' not in json.dumps(r)


def test_cap_and_coverage_not_scientific_exhaustion():
    r=summarize({'data':{'truncated':True},'source_diagnostics':[{'source':'ilthermo','status':'partial','records':1,'requests':[]}]},['ilthermo'],requested=('ilthermo',))
    assert r['sources'][0]['truncated'] and r['sources'][0]['coverage_limited']
    r=summarize({'pagination':[{'source':'scopus','stop_reason':'per_source_limit_reached'}],
                 'results_truncated':True,'eligible_articles_before_limit':12,'articles_returned':3,
                 'source_diagnostics':[{'source':'scopus','status':'returned_data','records':12}]},['scopus'])
    assert r['results_truncated'] and r['sources'][0]['coverage_limited']
    assert not r['sources'][0]['truncated'] # No claim that missing source records are known.


def test_partial_source_and_recovered_bad_query():
    r=summarize({'source_diagnostics':[{'source':'a','status':'returned_data','records':2,
       'requests':[{'http_status':200,'initial_http_status':400,'attempts':2,'cache':'miss'}]},
       {'source':'a','status':'request_failed','requests':[{'http_status':503,'attempts':1}]}]},['a'])
    assert r['sources'][0]['state']=='partial' and r['sources'][0]['recovered_query_errors']==1


@pytest.mark.parametrize('status',['missing_key','skipped_opt_in','identity_unresolved','empty_or_unparsed'])
def test_unavailable_never_becomes_no_matches(status):
    r=summarize({'source_diagnostics':[{'source':'a','status':status,'requests':[]}]},['a'])
    assert r['sources'][0]['state']=='unavailable' and r['sources'][0]['records_returned'] is None


def test_no_matches_only_when_reported_and_no_probe_claim():
    r=summarize({'source_diagnostics':[{'source':'a','status':'no_matches','records':0,'requests':[{'http_status':200,'attempts':1}]}]},['a','b'])
    assert r['sources'][0]['state']=='successful' and r['sources'][0]['records_returned']==0
    assert r['sources'][1]['state']=='untested'


def test_summary_is_per_result_not_stale_runtime_state():
    r=summarize({'source_diagnostics':[]},['a'],requested=('a',))
    assert r['sources'][0]['state']=='untested' and r['sources'][0]['untested_reason']=='no_diagnostic_record'


def test_fulltext_outcomes_and_storage_in_summary():
    r=summarize({'access_summary':{'outcome':'access_forbidden','institutional_entitlement':'not_verified'},
                 'fulltext_collection':{'requested':2,'readable':1,'records':[{'status':'success','retrieval':{'access_summary':{'outcome':'validated_pdf'}}},{'status':'browser_required','access_summary':{'outcome':'authentication_required'}}]},
                 'project_library':{'status':'saved'}},[])
    assert r['fulltext']['outcome']=='access_forbidden'
    assert r['fulltext_collection']['outcomes']=={'validated_pdf':1,'authentication_required':1}
    assert r['storage_status']=='saved'


def test_ilthermo_probe_is_bounded(monkeypatch):
    calls=[]
    monkeypatch.setattr(runtime.hub,'query_ilthermo',lambda q,**kw:calls.append(kw))
    runtime.query_source('ilthermo','EMIM TFSI',probe=True)
    assert calls==[{'max_sets':1}]


def test_unpaywall_skipped_opt_in_visible(monkeypatch):
    monkeypatch.delenv('CHEM_MAT_HUB_UNPAYWALL_EMAIL',raising=False)
    before=len(runtime.DIAGNOSTICS)
    assert runtime.hub.resolve_unpaywall_pdf('10.1234/a') is None
    assert runtime.DIAGNOSTICS[before]['status']=='skipped_opt_in'


def test_partial_dictionary_not_lost_when_one_request_fails():
    def fake():
        runtime.LOCAL.trace.append({'http_status':503,'host':'example.invalid'})
        return {'status':'partial','sets_retrieved':1}
    runtime.wrap('ilthermo',fake,None)()
    assert runtime.DIAGNOSTICS[-1]['status']=='partial'


def test_cli_doctor_does_not_claim_network_health(monkeypatch,tmp_path):
    runtime.DIAGNOSTICS.append({'source':'scopus','status':'returned_data','records':9})
    monkeypatch.setattr(runtime,'doctor',lambda:{'credentials':{'SCOPUS_KEY':True}})
    output=tmp_path/'doctor.json'
    monkeypatch.setattr(sys,'argv',['hub','--doctor','--output',str(output)])
    runtime.main()
    data=json.loads(output.read_text(encoding='utf-8'))
    assert data['diagnostic_summary']['counts']=={'untested':len(runtime.SOURCES)}


def test_cli_partial_property_summary(monkeypatch,tmp_path):
    def query(source,text,**kwargs):
        runtime.DIAGNOSTICS.append({'source':source,'status':'partial','records':1,'requests':[]})
        return {'status':'partial','truncated':True,'sets_retrieved':1}
    monkeypatch.setattr(runtime,'query_source',query)
    output=tmp_path/'property.json'
    monkeypatch.setattr(sys,'argv',['hub','--database','ilthermo','--query','EMIM DCA','--no-library','--output',str(output)])
    runtime.main()
    data=json.loads(output.read_text(encoding='utf-8'))
    source=next(s for s in data['diagnostic_summary']['sources'] if s['source']=='ilthermo')
    assert source['truncated'] and source['records_returned']==1
