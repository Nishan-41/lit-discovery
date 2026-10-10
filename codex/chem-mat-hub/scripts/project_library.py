"""Persistent project paper library, discovery history, and typed research graph."""
import hashlib
import html
import json
import os
import re
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def default_root():
    if os.environ.get('CHEM_MAT_HUB_LIBRARY_DIR'):
        return Path(os.environ['CHEM_MAT_HUB_LIBRARY_DIR'])
    config = Path(__file__).resolve().parent.parent/'references/library-default.json'
    if config.is_file():
        return Path(json.loads(config.read_text(encoding='utf-8'))['directory'])
    return Path.cwd()/'research-library'


def doi(value):
    value = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', str(value or '').strip(), flags=re.I)
    return value.lower() if re.fullmatch(r'10\.\d{4,9}/\S+', value) else None


def title_key(value):
    return re.sub(r'\W+', '', str(value or '').casefold())


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.tmp-'+uuid.uuid4().hex[:16])
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary,path)


class Library:
    def __init__(self, root):
        self.root=Path(root).resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        for name in ('papers','runs','pdfs','evidence','graph'):
            (self.root/name).mkdir(exist_ok=True)
        self.db=sqlite3.connect(self.root/'library.sqlite3',timeout=30)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
CREATE TABLE IF NOT EXISTS papers(id TEXT PRIMARY KEY,doi TEXT UNIQUE,title_key TEXT,data TEXT,first_seen TEXT,last_seen TEXT,state TEXT);
CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,created TEXT,kind TEXT,query TEXT,source TEXT,import_hash TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS imported_runs ON runs(source,import_hash) WHERE source IS NOT NULL;
CREATE TABLE IF NOT EXISTS edges(source TEXT,target TEXT,kind TEXT,run_id TEXT,PRIMARY KEY(source,target,kind,run_id));
CREATE TABLE IF NOT EXISTS assets(paper_id TEXT,path TEXT,role TEXT,sha256 TEXT,created TEXT,PRIMARY KEY(paper_id,sha256,role));
''')

    def close(self):
        self.db.close()

    def paper(self, article, timestamp):
        d=doi(article.get('doi'))
        key=title_key(article.get('title'))
        if not d and not key:
            return None
        row=self.db.execute('SELECT id,data,state FROM papers WHERE doi=?',(d,)).fetchone() if d else None
        if row is None and key:
            matches=self.db.execute('SELECT id,data,state,doi FROM papers WHERE title_key=?',(key,)).fetchall()
            compatible=[r for r in matches if not d or not r[3]]
            if len(compatible)==1:
                row=compatible[0][:3]
        identifier=row[0] if row else 'paper:'+hashlib.sha256((d or key).encode()).hexdigest()[:20]
        data=json.loads(row[1]) if row else {}
        for field,value in article.items():
            if field=='title' and value==d and data.get('title') and data['title']!=d:
                continue
            if value is not None and value != '' and (field!='abstract' or len(str(value))>len(str(data.get(field,'')))):
                if field=='source_databases':
                    value=sorted(set(data.get(field,[]))|set(value))
                data[field]=value
        if d:
            data['doi']=d
        data.setdefault('title',d or key)
        state=row[2] if row else 'discovered'
        self.db.execute('INSERT INTO papers VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET doi=coalesce(excluded.doi,papers.doi),title_key=excluded.title_key,data=excluded.data,last_seen=excluded.last_seen',
                        (identifier,d,title_key(data['title']),json.dumps(data,ensure_ascii=False),timestamp,timestamp,state))
        return identifier

    def ingest(self,result,kind='search',query=None,source=None,paper_doi=None,asset_role='main'):
        timestamp=now()
        digest=hashlib.sha256(json.dumps(result,sort_keys=True,default=str).encode()).hexdigest()
        if source and self.db.execute('SELECT id FROM runs WHERE source=? AND import_hash=?',(source,digest)).fetchone():
            return {'status':'already_imported','library':str(self.root)}
        run='run:'+uuid.uuid4().hex
        query=query or result.get('query') or result.get('target_query') or result.get('seed_work',{}).get('query') or kind
        with self.db:
            self.db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?)',(run,timestamp,kind,str(query),source,digest if source else None))
            articles=result.get('articles') or result.get('connected_works') or []
            seed=None
            if result.get('seed_work'):
                raw=result['seed_work']
                seed=self.paper({'title':raw.get('title'),'doi':doi(raw.get('query')),'openalex_id':raw.get('openalex_id')},timestamp)
            for article in articles:
                identifier=self.paper(article,timestamp)
                if not identifier:
                    continue
                self.db.execute('INSERT OR IGNORE INTO edges VALUES(?,?,?,?)',(run,identifier,'discovered_in',run))
                if seed and seed!=identifier:
                    mode=result.get('graph_mode')
                    if mode=='cites':
                        edge=(identifier,seed,'cites',run)
                    elif mode=='cited_by':
                        edge=(seed,identifier,'cites',run)
                    else:
                        edge=(seed,identifier,'related_by_openalex',run)
                    self.db.execute('INSERT OR IGNORE INTO edges VALUES(?,?,?,?)',edge)
            if kind=='reading' or result.get('pages') is not None or result.get('saved_pdf'):
                d=doi(paper_doi) or doi(result.get('target_query')) or doi(query)
                title=result.get('title') or d or Path(str(result.get('target_query','Unknown paper'))).name
                identifier=self.paper({'title':title,'doi':d},timestamp)
                if identifier:
                    self.attach(identifier,result,asset_role,timestamp)
                    self.db.execute('INSERT OR IGNORE INTO edges VALUES(?,?,?,?)',(run,identifier,'extracted_in',run))
            for record in result.get('fulltext_collection',{}).get('records',[]):
                identifier=self.paper(record,timestamp)
                evidence_file=record.get('evidence_file')
                if identifier and evidence_file and Path(evidence_file).is_file():
                    evidence=json.loads(Path(evidence_file).read_text(encoding='utf-8'))
                    self.attach(identifier,evidence,'main',timestamp)
        atomic_json(self.root/'runs'/(run[4:]+'.json'),{'created':timestamp,'kind':kind,'query':query,'import_source':source,'result':result})
        self.export()
        return {'status':'saved','library':str(self.root),'run_id':run,'papers':self.db.execute('SELECT count(*) FROM papers').fetchone()[0], 'runs':self.db.execute('SELECT count(*) FROM runs').fetchone()[0]}

    def attach(self,identifier,result,role,timestamp):
        evidence=dict(result)
        source=result.get('saved_pdf')
        if source and Path(source).is_file():
            body=Path(source).read_bytes()
            checksum=hashlib.sha256(body).hexdigest()
            try:
                Path(source).resolve().relative_to(self.root)
                destination=Path(source).resolve()
            except ValueError:
                destination=self.root/'pdfs'/(checksum+'.pdf')
            if not destination.exists():
                with destination.open('xb') as stream:
                    stream.write(body)
            evidence['saved_pdf']=str(destination)
            self.db.execute('INSERT OR IGNORE INTO assets VALUES(?,?,?,?,?)',(identifier,str(destination.relative_to(self.root)),role,checksum,timestamp))
        checksum=hashlib.sha256(json.dumps(evidence,sort_keys=True,default=str).encode()).hexdigest()
        evidence_path=self.root/'evidence'/(checksum+'.json')
        atomic_json(evidence_path,evidence)
        self.db.execute('INSERT OR IGNORE INTO assets VALUES(?,?,?,?,?)',(identifier,str(evidence_path.relative_to(self.root)),role+'_evidence',checksum,timestamp))
        if role=='main' and result.get('pages_read',0)>0:
            state='text_extracted_partial' if result.get('truncated') or result.get('status')=='partial' else 'text_extracted'
            self.db.execute('UPDATE papers SET state=?,last_seen=? WHERE id=?',(state,timestamp,identifier))

    def graph(self):
        nodes=[]
        for identifier,data,first,last,state in self.db.execute('SELECT id,data,first_seen,last_seen,state FROM papers ORDER BY first_seen,id'):
            article=json.loads(data)
            assets=[{'path':p,'role':role,'created':at} for p,role,at in self.db.execute('SELECT path,role,created FROM assets WHERE paper_id=?',(identifier,))]
            nodes.append({'id':identifier,'type':'paper','title':article.get('title'),'doi':article.get('doi'),'year':article.get('year'),'first_seen':first,'last_seen':last,'state':state,'assets':assets})
        for identifier,created,kind,query in self.db.execute('SELECT id,created,kind,query FROM runs ORDER BY created'):
            nodes.append({'id':identifier,'type':'run','title':query,'kind':kind,'first_seen':created})
        edges=[{'source':s,'target':t,'kind':k,'run_id':r} for s,t,k,r in self.db.execute('SELECT source,target,kind,run_id FROM edges')]
        return {'generated':now(),'nodes':nodes,'edges':edges,'note':'Discovery edges indicate a saved search; cites edges come only from citation-source records. Extraction is not scientific review.'}

    def export(self):
        graph=self.graph()
        atomic_json(self.root/'graph/network.json',graph)
        for identifier,data,first,last,state in self.db.execute('SELECT id,data,first_seen,last_seen,state FROM papers'):
            atomic_json(self.root/'papers'/(identifier.split(':')[1]+'.json'),{'id':identifier,'first_seen':first,'last_seen':last,'state':state,'metadata':json.loads(data)})
        template=Path(__file__).with_name('library_graph.html').read_text(encoding='utf-8')
        payload=json.dumps(graph,ensure_ascii=False).replace('<','\\u003c')
        output=template.replace('__GRAPH_DATA__',payload)
        destination=self.root/'graph/network.html'
        temporary=destination.with_suffix('.'+uuid.uuid4().hex+'.tmp')
        temporary.write_text(output,encoding='utf-8')
        os.replace(temporary,destination)
        return str(destination)
