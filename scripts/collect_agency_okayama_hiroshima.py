#!/usr/bin/env python3
"""Collect public official Okayama listings and fact tables, preserving their scope."""
import sys,json,hashlib,re,threading,time,runpy,collections,urllib.request,urllib.parse,urllib.error
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
REPO=Path(__file__).resolve().parents[1]
OUT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else REPO.parent/'national-research/agency-west/okayama-hiroshima'
OUT.mkdir(parents=True,exist_ok=True)
CACHE=OUT.parent/'cache';CACHE.mkdir(parents=True,exist_ok=True)
PARSER=runpy.run_path(str(REPO/'scripts/collect_tottori.py'));Page=PARSER['Page'];Node=PARSER['Node']
LOCKS=collections.defaultdict(threading.Lock);LAST=collections.defaultdict(float)
def fetch(url):
    path=CACHE/(hashlib.sha256(url.encode()).hexdigest()+'.html')
    if path.exists():return path.read_text()
    host=urllib.parse.urlsplit(url).netloc
    error=None
    for attempt in range(2):
        with LOCKS[host]:
            pause=.35-(time.monotonic()-LAST[host])
            if pause>0:time.sleep(pause)
            LAST[host]=time.monotonic()
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'ShrineAtlasResearch/0.3 (+https://github.com/sumeragisakan/shrine-atlas)'})
            with urllib.request.urlopen(req,timeout=30) as response:
                body=response.read();encoding=response.headers.get_content_charset()
            if not encoding:
                match=re.search(br'charset=[\"\']?([\w-]+)',body[:10000]);encoding=match[1].decode() if match else 'utf-8'
            try:html=body.decode(encoding)
            except (UnicodeDecodeError,LookupError):
                try:html=body.decode('utf-8')
                except UnicodeDecodeError:html=body.decode('cp932',errors='replace')
            path.write_text(html);return html
        except urllib.error.HTTPError as exc:
            error=exc
            if exc.code in (400,401,403,404):break
        except Exception as exc:error=exc
        if attempt==0:time.sleep(1)
    raise RuntimeError(str(error))
def links(html,url):
    return [(a.text(),urllib.parse.urljoin(url,a.attrs['href'])) for a in Page(html).root.nodes('a') if a.attrs.get('href')]
def rec(name,address,index_url,profile_url=None,source_id=None,**kw):
    row=dict(source_id=source_id or profile_url or index_url,name=name,kana=None,address=address or None,address_legacy=None,kami_verbatim=None,rank=None,profile_url=profile_url,index_url=index_url,lat=None,lon=None,coordinate_source_url=None,source_sha256=None)
    row.update(kw);return row

BASE='https://www.okayama-jinjacho.or.jp/search/list/'

def field_sources(record):
    record['field_source_urls']={
        field:(record['index_url'] if field in ('name','kana','address') else record['profile_url']) if record.get(field) is not None else None
        for field in ('name','kana','address','kami_verbatim','rank','lat','lon')
    }
    return record


def save(records,indexes,errors,finished=False):
 o=dict(code='33',name='岡山県',provider='岡山県神社庁',label='公式・全件一覧表示',index_urls=sorted(indexes),scope_note='岡山県神社庁の全件一覧表示に掲載された1609件。公開ディレクトリの収録範囲であり県内の全神社を保証しない。祭神・旧社格・座標は公開詳細ページの明記値のみ。',expected_rows=1609,pagination_complete=finished,records=[field_sources(r) for r in sorted(records.values(),key=lambda r:r['source_id'])],failures=errors)
 o['detail_scope_note']='1609 linked profile pages; detail collection status is separate from81-page directory pagination.'
 p=OUT/'33-okayama.json';p.write_text(json.dumps(o,ensure_ascii=False,indent=2));return o

def rows(html,url):
 out=[];page=Page(html)
 for a in page.root.nodes('a'):
  if 'shrineList__row' not in a.attrs.get('class',''):continue
  cells=[c for c in a.children if isinstance(c,Node) and c.tag=='div' and 'shrineList__cell' in c.attrs.get('class','')]
  if len(cells)<5:raise ValueError('Invalid shrine list structure')
  code=cells[0].text();name=cells[1].text();kana=cells[2].text() or None
  ads=[n.text() for n in cells[4].nodes('span') if n.attrs.get('class')=='item-address']
  address=ads[0] if ads else None
  out.append(rec(name,address,url,a.attrs['href'],code,kana=kana,source_sha256=hashlib.sha256(html.encode()).hexdigest()))
 return out

def detail(html,url,expected_id=None):
 p=Page(html);fields={}
 for tr in p.root.nodes('tr'):
  cells=[c for c in tr.children if isinstance(c,Node) and c.tag in ('th','td')]
  if len(cells)==2:fields[re.sub(r'\s+','',cells[0].text())]=cells[1].raw().strip()
 if '神社コード' not in fields:raise ValueError('Missing shrine code on detail page')
 if expected_id is not None and fields['神社コード']!=expected_id:raise ValueError('Detail shrine code mismatch')
 d={'kami_verbatim':fields.get('御祭神') or None,'rank':fields.get('旧社格') or None,'source_sha256':hashlib.sha256(html.encode()).hexdigest()}
 points=[]
 for a in p.root.nodes('a'):
  m=re.match(r'https://www\.google\.com/maps/place/(-?[0-9]+(?:\.[0-9]+)?),(-?[0-9]+(?:\.[0-9]+)?)$',a.attrs.get('href',''))
  if m:points.append((float(m[1]),float(m[2])))
 if len(set(points))==1:
  d.update(lat=points[0][0],lon=points[0][1],coordinate_source_url=url)
 return d

def main():
 records={};indexes={};errors=[{'kind':'optional_api','url':'https://www.okayama-jinjacho.or.jp/wp/wp-admin/admin-ajax.php?ajaxid=1','error':'HTTP403 from public map endpoint; HTML directory and profile pages used instead.'}];pending_indexes=[BASE];seen=set();detail_queue=[];detail_seen=set();done_details=0
 with ThreadPoolExecutor(max_workers=8) as pool:
  running={}
  while pending_indexes or detail_queue or running:
   while len(running)<8 and (pending_indexes or detail_queue):
    if pending_indexes:
     u=pending_indexes.pop(0)
     if u in seen:continue
     seen.add(u);kind='index'
    else:
     u=detail_queue.pop(0)
     if u in detail_seen:continue
     detail_seen.add(u);kind='detail'
    running[pool.submit(fetch,u)]=(kind,u)
   if not running:continue
   completed,_=wait(running,timeout=30,return_when=FIRST_COMPLETED)
   for f in completed:
    kind,u=running.pop(f)
    try:
     html=f.result()
     if not html:raise RuntimeError('Source returned server error after retry')
     if kind=='index':
      entries=rows(html,u)
      if not entries:raise RuntimeError('Empty source list')
      indexes[u]=len(entries)
      for r in entries:
       records[r['source_id']]=r
       detail_queue.append(r['profile_url'])
      for _,link in links(html,u):
       if re.fullmatch(re.escape(BASE)+r'(?:page/\d+/)?',link) and link not in seen:pending_indexes.append(link)
      print('INDEX',len(indexes),'ROWS',len(records),'RUNNING',len(running),flush=True)
     else:
      entry=next((r for r in records.values() if r['profile_url']==u),None)
      if entry:entry.update(detail(html,u,entry['source_id']))
      done_details+=1
      if done_details%50==0:print('DETAIL',done_details,'ROWS',len(records),flush=True)
    except Exception as e:
     errors.append({'kind':kind,'url':u,'error':str(e)});print('ERROR',kind,u,str(e),flush=True)
     if 'Tunnel connection failed: 403 Forbidden' in str(e):
      for queued in dict.fromkeys(detail_queue):
       if queued not in detail_seen:errors.append({'kind':'detail_not_attempted','url':queued,'error':'Not requested after repeated proxy tunnel403 stopped host collection.'})
      detail_queue.clear();pending_indexes.clear()
      print('STOP_HOST proxy tunnel403',flush=True)
   if completed:save(records,indexes,errors,False)
 save(records,indexes,errors,len(indexes)==81 and len(records)==1609)
 print('DONE',len(records),len(indexes),done_details,len(errors),flush=True)



def collect_hiroshima():
    url='https://www.hiroshima-jinjacho.jp/branch/saeki-otake/'
    html=fetch(url);records=[]
    for number,tr in enumerate(Page(html).root.nodes('tr')):
        cells=[c for c in tr.children if isinstance(c,Node) and c.tag in ('th','td')]
        if len(cells)!=2 or cells[0].tag!='td':continue
        name,address=cells[0].text(),cells[1].text()
        if not name or not address:continue
        anchors=list(cells[0].nodes('a'))
        profile=urllib.parse.urljoin(url,anchors[0].attrs['href']) if anchors else None
        source_id=profile or 'saeki-otake:'+hashlib.sha256((name+'\n'+address).encode()).hexdigest()[:16]
        records.append(rec(name,address,url,profile,source_id,source_sha256=hashlib.sha256(html.encode()).hexdigest()))
    profiles=sorted({r['profile_url'] for r in records if r['profile_url']})
    details={};errors=[{'kind':'prefectural_index','url':'https://www.hiroshima-jinjacho.jp/hirosima_jinja/','error':'HTTP500 データベース接続確立エラー; no prefectural directory rows imported.'}]
    with ThreadPoolExecutor(max_workers=6) as pool:
        tasks={pool.submit(fetch,u):u for u in profiles}
        for future,u in tasks.items():
            try:details[u]=future.result()
            except Exception as exc:errors.append({'kind':'detail','url':u,'error':str(exc)})
    for row in records:
        detail_html=details.get(row['profile_url'])
        if not detail_html:continue
        for tr in Page(detail_html).root.nodes('tr'):
            cells=[c for c in tr.children if isinstance(c,Node) and c.tag in ('th','td')]
            if len(cells)==2 and re.sub(r'\s+','',cells[0].text())=='御祭神':
                row['kami_verbatim']=cells[1].raw().strip() or None
        row['source_sha256']=hashlib.sha256(detail_html.encode()).hexdigest()
    obj=dict(code='34',name='広島県',provider='広島県神社庁佐伯大竹支部',label='公式・佐伯大竹支部神社一覧',index_urls=[url],scope_note='佐伯大竹支部の一覧99社を全件収録。広島県全域ではない。県全域ディレクトリはデータベース接続エラーで取得不能。リンクのある公開詳細ページの御祭神欄のみ追加。',expected_rows=99,pagination_complete=len(records)==99,records=records,failures=errors)
    obj['records']=[field_sources(r) for r in records]
    obj['detail_pages_total']=len(profiles);obj['detail_pages_loaded']=len(details);obj['detail_pages_complete']=len(details)==len(profiles)
    obj['detail_completion']={'listed_profiles':len(profiles),'fetched_profiles':len(details),'failed_profiles':len(profiles)-len(details),'complete':len(details)==len(profiles)}
    (OUT/'34-hiroshima-saeki-otake.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2))
    print('HIROSHIMA',len(records),len(details),flush=True)

def finalize_okayama():
    path=OUT/'33-okayama.json'
    obj=json.loads(path.read_text());loaded=0;failures=obj['failures']
    for row in obj['records']:
        cached=CACHE/(hashlib.sha256(row['profile_url'].encode()).hexdigest()+'.html')
        if cached.exists():
            try:
                row.update(detail(cached.read_text(),row['profile_url'],row['source_id']));loaded+=1
            except Exception as exc:
                failures.append({'kind':'detail_validation','url':row['profile_url'],'error':str(exc)})
                for field in ('kami_verbatim','rank','lat','lon','coordinate_source_url'):row[field]=None
        field_sources(row)
    api_failure={'kind':'optional_api','url':'https://www.okayama-jinjacho.or.jp/wp/wp-admin/admin-ajax.php?ajaxid=1','error':'HTTP403 from public map endpoint; HTML directory and profile pages used instead.'}
    if not any(f.get('kind')=='optional_api' for f in failures):failures.append(api_failure)
    obj['pagination_complete']=len(obj['index_urls'])==81 and len(obj['records'])==1609
    obj['detail_pages_total']=1609;obj['detail_pages_loaded']=loaded;obj['detail_pages_complete']=loaded==1609
    obj['detail_completion']={'listed_profiles':1609,'fetched_profiles':loaded,'failed_profiles':len({f['url'] for f in failures if f.get('kind') in ('detail','detail_validation')}),'not_attempted_profiles':len({f['url'] for f in failures if f.get('kind')=='detail_not_attempted'}),'complete':loaded==1609}
    obj['detail_scope_note']=str(loaded)+'/1609 linked profile pages parsed. Directory pagination (81 pages) and detail-page enrichment have separate completion status. Missing fields remain null.'
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2))
    print('FINALIZED_OKAYAMA',len(obj['records']),loaded,len(failures),flush=True)

if __name__=='__main__':
    main()
    finalize_okayama()
    collect_hiroshima()
