"""One credential-safe health/coverage summary; untested never means healthy."""
from collections import Counter, defaultdict


FAILURES = {'request_failed','parse_or_runtime_error','adapter_parse_failed','schema_error','error','timeout'}
UNAVAILABLE = {'missing_key','skipped','skipped_opt_in','not_found','identity_unresolved','empty_or_unparsed'}
BUDGET_STOPS = {'per_source_limit_reached','page_budget_reached'}


def summarize(result, source_names, *, requested=(), observations=None):
    observed=defaultdict(list)
    for row in result.get('source_diagnostics',[]) if observations is None else observations:
        if isinstance(row,dict) and row.get('source'):observed[row['source']].append(row)
    pagination=defaultdict(list)
    for row in result.get('pagination',[]):
        if row.get('source'):pagination[row['source']].append(row)
    sources=[]
    for name in sorted(set(source_names)|set(observed)):
        logs=observed[name];requests=[r for log in logs for r in log.get('requests',[]) if isinstance(r,dict)]
        statuses=list(dict.fromkeys(log.get('status','unknown') for log in logs))
        hits=sum(r.get('cache')=='hit' for r in requests)
        misses=sum(r.get('cache')=='miss' for r in requests)
        counts=[r['records'] for r in logs if isinstance(r.get('records'),int)]
        bounded=any(p.get('stop_reason') in BUDGET_STOPS for p in pagination[name])
        truncated=False
        if isinstance(result.get('data'),dict) and len(requested)==1 and name in requested:
            data=result['data'];truncated=bool(data.get('truncated'))
        success=any(s in ('returned_data','no_matches') for s in statuses)
        failure=any(s in FAILURES for s in statuses)
        if not logs:state='untested'
        elif 'partial' in statuses or (success and failure):state='partial'
        elif failure:state='failed'
        elif truncated:state='truncated'
        elif success:state='successful'
        elif any(s in UNAVAILABLE for s in statuses):state='unavailable'
        else:state='unknown'
        failures=[]
        for r in requests:
            code=r.get('http_status')
            if r.get('error_type') or isinstance(code,int) and code>=400:
                # No URL, server body, cookie, header or query string copied here.
                failures.append({k:r[k] for k in ('host','http_status','error_type','api_error_code') if k in r})
        sources.append({'source':name,'state':state,'adapter_called':bool(logs),
            'network_tested':any(r.get('attempts',1)>0 and r.get('cache')!='hit' for r in requests),
            'requested':name in requested,'detail_statuses':statuses,
            'records_returned':sum(counts) if counts else None,
            'truncated':truncated,'coverage_limited':bounded or truncated,
            'stop_reasons':list(dict.fromkeys(p.get('stop_reason') for p in pagination[name])),
            'request_count':len(requests),'cached_requests':hits,
            'cache_state':'all_hits' if requests and hits==len(requests) else 'mixed' if hits else 'miss' if misses else 'not_applicable',
            'recovered_query_errors':sum(bool(r.get('initial_http_status')) and r.get('http_status',999)<400 for r in requests),
            'failures':failures,
            'untested_reason':('not_requested' if name not in requested else 'no_diagnostic_record') if not logs else None})
    counts=Counter(s['state'] for s in sources)
    summary={'scope':'this operation only; not a universal service-health or entitlement audit',
        'counts':dict(counts),'cached_sources':sum(s['cached_requests']>0 for s in sources),
        'coverage_limited_sources':sum(s['coverage_limited'] for s in sources),
        'results_truncated':bool(result.get('results_truncated')),
        'returned_articles':result.get('articles_returned'),
        'eligible_articles_before_limit':result.get('eligible_articles_before_limit'),
        'sources':sources,
        'coverage_note':'Budget stop reasons indicate bounded retrieval, not proof of scientific exhaustion. Cache hits do not test current network access.'}
    retrieval=result.get('retrieval',{})
    if result.get('access_summary') or retrieval.get('access_summary'):
        summary['fulltext']=result.get('access_summary') or retrieval['access_summary']
    collection=result.get('fulltext_collection')
    if collection:
        summary['fulltext_collection']={'requested':collection.get('requested'), 'readable':collection.get('readable'),
            'outcomes':dict(Counter((r.get('access_summary') or r.get('retrieval',{}).get('access_summary') or {}).get('outcome',r.get('status','unknown')) for r in collection.get('records',[])))}
    if result.get('project_library'):summary['storage_status']=result['project_library'].get('status')
    return summary


def attach(result, source_names, *, requested=(), observations=None):
    result['diagnostic_summary']=summarize(result,source_names,requested=requested,observations=observations)
    return result
