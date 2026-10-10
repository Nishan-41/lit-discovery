import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from project_library import Library


def test_search_accumulation_dedup_and_import_idempotence(tmp_path):
    library=Library(tmp_path/'library')
    try:
        first={'query':'ionogel','articles':[{'title':'Ionogel transport','doi':'https://doi.org/10.1234/A','abstract':'Short'}]}
        library.ingest(first,source='original.json')
        assert library.ingest(first,source='original.json')['status']=='already_imported'
        library.ingest({'query':'polymer','articles':[{'title':'Ionogel transport','doi':'10.1234/a','abstract':'A longer real abstract'}]})
        graph=library.graph()
        assert len([n for n in graph['nodes'] if n['type']=='paper'])==1
        assert len([n for n in graph['nodes'] if n['type']=='run'])==2
        assert all(e['kind']=='discovered_in' for e in graph['edges'])
        assert (library.root/'graph/network.html').is_file()
        assert (library.root/'runs').glob('*.json')
    finally:
        library.close()


def test_citation_direction_and_related_are_distinct(tmp_path):
    library=Library(tmp_path)
    try:
        seed={'title':'Seed','query':'10.1234/seed'}
        library.ingest({'seed_work':seed,'graph_mode':'cites','connected_works':[{'title':'Newer','doi':'10.1234/new'}]})
        library.ingest({'seed_work':seed,'graph_mode':'cited_by','connected_works':[{'title':'Older','doi':'10.1234/old'}]})
        library.ingest({'seed_work':seed,'graph_mode':'related_to','connected_works':[{'title':'Related','doi':'10.1234/related'}]})
        graph=library.graph(); titles={n['id']:n['title'] for n in graph['nodes']}
        pairs={(titles[e['source']],titles[e['target']],e['kind']) for e in graph['edges'] if e['kind']!='discovered_in'}
        assert ('Newer','Seed','cites') in pairs
        assert ('Seed','Older','cites') in pairs
        assert ('Seed','Related','related_by_openalex') in pairs
    finally:
        library.close()


def test_pdf_evidence_roles_preserve_metadata(tmp_path):
    library=Library(tmp_path/'library')
    pdf=tmp_path/'download.pdf'; pdf.write_bytes(b'fixture bytes')
    try:
        library.ingest({'articles':[{'title':'Real title','doi':'10.1234/a'}]})
        result={'target_query':'10.1234/a','saved_pdf':str(pdf),'pages':[{'page':1,'text':'Evidence'}],'pages_read':1,'status':'success'}
        library.ingest(result,kind='reading')
        library.ingest(result,kind='reading',asset_role='supporting')
        paper=[n for n in library.graph()['nodes'] if n['type']=='paper'][0]
        assert paper['title']=='Real title'
        assert paper['state']=='text_extracted'
        assert {'main','supporting','main_evidence','supporting_evidence'}=={a['role'] for a in paper['assets']}
        assert len(list((library.root/'pdfs').glob('*.pdf')))==1
    finally:
        library.close()


def test_same_title_distinct_dois_remain_distinct(tmp_path):
    library=Library(tmp_path)
    try:
        library.ingest({'articles':[{'title':'Common title','doi':'10.1234/a'},{'title':'Common title','doi':'10.1234/b'}]})
        assert len([n for n in library.graph()['nodes'] if n['type']=='paper'])==2
    finally:
        library.close()


def test_graph_payload_escapes_script_content(tmp_path):
    library=Library(tmp_path)
    try:
        library.ingest({'articles':[{'title':'</script><script>alert(1)</script>','doi':'10.1234/a'}]})
        output=(library.root/'graph/network.html').read_text(encoding='utf-8')
        assert '</script><script>alert(1)</script>' not in output
        assert '__GRAPH_DATA__' not in output
    finally:
        library.close()
