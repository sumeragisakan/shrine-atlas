#!/usr/bin/env python3
"""Cache public western agency facts outside the app checkout.
Usage: python collect_agency_west.py OUTPUT_DIRECTORY [32 32-profiles 40 41 42 47]
Only factual fields are emitted; raw narrative-bearing pages stay in the local research cache.
"""
import sys,json,hashlib,urllib.request,urllib.parse,urllib.error,re,runpy,time,threading,collections
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
M=runpy.run_path(str(Path(__file__).resolve().with_name('collect_tottori.py')));Page=M['Page'];Node=M['Node']
ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[2]/'national-research/agency-west';CACHE=ROOT/'cache';CACHE.mkdir(parents=True,exist_ok=True)
locks=collections.defaultdict(threading.Lock);last=collections.defaultdict(float)
def fetch(url,data=None):
 payload=urllib.parse.urlencode(data).encode() if data is not None else None
 key=hashlib.sha256((url+(('\n'+payload.decode()) if payload else '')).encode()).hexdigest();p=CACHE/(key+'.html')
 if p.exists():return p.read_text()
 host=urllib.parse.urlsplit(url).netloc
 for n in range(2):
  with locks[host]:
   pause=.35-(time.monotonic()-last[host])
   if pause>0:time.sleep(pause)
   last[host]=time.monotonic()
  try:
   with urllib.request.urlopen(urllib.request.Request(url,data=payload,headers={'User-Agent':'ShrineAtlasResearch/0.3 (+https://github.com/sumeragisakan/shrine-atlas)'}),timeout=30) as r:
    b=r.read();enc=r.headers.get_content_charset()
   if not enc:
    m=re.search(br'charset=["\']?([\w-]+)',b[:10000]);enc=m[1].decode() if m else 'utf-8'
   try:s=b.decode(enc)
   except(UnicodeDecodeError,LookupError):
    try:s=b.decode('utf-8')
    except UnicodeDecodeError:s=b.decode('cp932',errors='replace')
   p.write_text(s);return s
  except urllib.error.HTTPError as e:
   if e.code in (400,401,403,404):raise
   if n==1:raise
  except Exception:
   if n==1:raise
  time.sleep(1)
def par(urls,fn=fetch,workers=8):
 out={};err=[]
 with ThreadPoolExecutor(max_workers=workers) as pool:
  fs={pool.submit(fn,u):u for u in urls}
  for f in as_completed(fs):
   u=fs[f]
   try:out[u]=f.result()
   except Exception as e:err.append({'url':u,'error':str(e)})
 return out,err
def links(s,url):return [(a.text(),urllib.parse.urljoin(url,a.attrs['href'])) for a in Page(s).root.nodes('a') if a.attrs.get('href')]
def rec(name,address,index_url,profile_url=None,source_id=None,**kw):
 d=dict(source_id=source_id or profile_url or index_url,name=name,kana=None,address=address or None,address_legacy=None,kami_verbatim=None,rank=None,profile_url=profile_url,index_url=index_url,lat=None,lon=None,coordinate_source_url=None,source_sha256=None);d.update(kw);return d
def result(code,name,provider,index_urls,scope_note,records,failures=[],complete=True,expected=None):

 for r in records:
  if 'field_source_urls' not in r:r['field_source_urls']={f:((r['index_url'] if str(code)=='32' else r.get('profile_url') or r['index_url']) if r.get(f) is not None else None) for f in ['name','kana','address','kami_verbatim','rank','lat','lon']}
 o=dict(code=str(code),name=name,provider=provider,label=provider,index_urls=index_urls,scope_note=scope_note,expected_rows=expected,pagination_complete=complete,records=records,failures=failures)
 p=ROOT/(str(code)+'-'+name+'.json');p.write_text(json.dumps(o,ensure_ascii=False,indent=2));print('SAVED',p,len(records),len(failures),flush=True);return o

def sha(s):return hashlib.sha256(s.encode()).hexdigest()
def cells(n):return [c for c in n.children if isinstance(c,Node) and c.tag in ('td','th')]
def shimane():
 base='https://www.shimane-jinjacho.or.jp/search/index.html';s=fetch(base)
 urls=list(dict.fromkeys(u for l,u in links(s,base) if re.fullmatch(r'.+[市町村]',l)))
 assert len(urls)==19,len(urls)
 pages,err=par(urls,workers=5);rows=[]
 for u in urls:
  if u not in pages:continue
  s=pages[u];p=Page(s)
  for i,tr in enumerate(p.root.nodes('tr')):
   cs=cells(tr)
   if len(cs)!=4 or cs[0].tag!='td' or not cs[0].text():continue
   # All four published cells are factual fields; retain deity text exactly apart from HTML whitespace.
   name=cs[0].text();a=next(cs[0].nodes('a'),None)
   profile=urllib.parse.urljoin(u,a.attrs['href']) if a and a.attrs.get('href') else u
   rows.append(rec(name,cs[2].text(),u,profile,u+'#row-'+str(i),kami_verbatim=cs[1].text() or None,source_sha256=sha(s)))
 result(32,'島根県','島根県神社庁',urls,'Published municipal tables across all 19 linked municipalities, exhausted. This is the agency directory scope, not a claim about every extant shrine. No coordinates published in these tables.',rows,err,not err)
def fukuoka():
 base='https://fukuoka-jinjacho.or.jp/';s=fetch(base);urls=list(dict.fromkeys(u for l,u in links(s,base) if '/area/' in u));assert len(urls)==4
 pages,err=par(urls,workers=4);rows=[]
 for u in urls:
  if u not in pages:continue
  s=pages[u];p=Page(s)
  for i,div in enumerate(n for n in p.root.nodes('div') if n.attrs.get('class')=='p-area-list__cont'):
   ps=list(div.nodes('p'));fs={c.attrs.get('class'):c for c in ps};n=fs.get('p-area-list__text');a=fs.get('p-area-list__add')
   if not n or not a:continue
   rows.append(rec(n.text(),a.text(),u,u,u+'#listing-'+str(i),source_sha256=sha(s)))
 result(40,'福岡県','福岡県神社庁',urls,'All four published regional shrine-introduction lists, exhausted. These selected introductions are smaller than the approximately 3,300 affiliated shrines described by the agency. The tables publish no deity or coordinate fields.',rows,err,not err)
def nagasaki():
 base='https://nagasaki-jinjacho.or.jp/search.html';s=fetch(base)
 urls=list(dict.fromkeys(urllib.parse.urldefrag(u)[0] for l,u in links(s,base) if '#' in u and re.search(r'/(?:tsushima|iki|kamigoyou|shimogotou|hirado|matsuura|sasebo|seihi|oomura|nagasaki|isahaya|shimabara)\.html#',u)))
 assert len(urls)==12,(len(urls),urls)
 pages,err=par(urls,workers=5);rows=[]
 for u in urls:
  if u not in pages:continue
  s=pages[u];p=Page(s)
  for i,tr in enumerate(p.root.nodes('tr')):
   cs=cells(tr)
   if len(cs)!=7 or not re.fullmatch(r'\d+',cs[0].text()):continue
   rows.append(rec(cs[1].text(),cs[6].text(),u,u,u+'#row-'+str(i),kami_verbatim=cs[2].text() or None,rank=cs[3].text() or None,source_sha256=sha(s)))
 result(42,'長崎県','長崎県神社庁',urls,'All twelve regional directories linked by the current official search index, exhausted. Each table publishes shrine/deity/former-rank/address facts; raw deity expressions including 外N柱 are retained. Directory scope only, not all extant shrines.',rows,err,not err)

def saga():
 u='https://saga-jinjacho.jp/jinja-map/';s=fetch(u);p=Page(s)
 hrefs=list(dict.fromkeys((a.text().lstrip('・'),urllib.parse.urljoin(u,a.attrs['href'])) for a in p.root.nodes('a') if a.attrs.get('href') and a.text().startswith('・')))
 pages,err=par([x[1] for x in hrefs],workers=6);rows=[]
 for name,url in hrefs:
  if url not in pages:
   rows.append(rec(name,None,u,url,url));continue
  s=pages[url];p=Page(s);txt=p.root.text();fields={}
  for m in re.finditer(r'【([^】]+)】\s*(.*?)(?=【|PAGETOP|$)',txt):fields[m[1]]=m[2].strip()
  r=rec(name,fields.get('鎮座地'),u,url,url,kami_verbatim=fields.get('祭神') or fields.get('御祭神') or fields.get('祭神御') or None,rank=fields.get('社格') or None,source_sha256=sha(s))
  r['profile_title']=next((h.text() for h in p.root.nodes('h1')),None)
  r['field_source_urls']={f:(u if f=='name' else url) if r.get(f) is not None else None for f in ['name','kana','address','kami_verbatim','rank','lat','lon']};rows.append(r)
 result(41,'佐賀県','佐賀県神社庁',[u],'Every published profile link on the regional introduction index, exhausted; selected directory scope, not all extant shrines. Published old municipal address spellings are retained verbatim.',rows,err,not err,expected=len(hrefs))

def okinawa():
 u='https://jinjacho.naminouegu.jp/';s=fetch(u);p=Page(s);rows=[];err=[]
 profiles={'末吉宮':'sueyoshi.html','天久宮':'ameku.html','八幡宮':'asato.html','浮島神社':'ukishima.html','世持神社':'yomochi.html','沖縄神社':'okinawajinja.html'}
 for n in p.root.nodes('p'):
  if not n.attrs.get('id') or n.attrs['id']=='shinsei':continue
  lines=[x.strip() for x in n.raw().splitlines() if x.strip()]
  if len(lines)<2:continue
  name,address=lines[:2];url=urllib.parse.urljoin(u,profiles[name]) if name in profiles else next((urllib.parse.urljoin(u,a.attrs['href']) for a in n.nodes('a') if a.attrs.get('href','').startswith('http')),u)
  r=rec(name,address,u,url,u+'#'+name,source_sha256=sha(s));r['field_source_urls']={f:(u if r.get(f) is not None else None) for f in ['name','kana','address','kami_verbatim','rank','lat','lon']}
  if name in profiles:
   try:
    ds=fetch(url);m=re.search(r'<h2\b[^>]*>\s*御祭神\s*</h2>(.*?)(?=<h2\b)',ds,re.S|re.I)
    if m:r['kami_verbatim']=Page(m[1]).root.text();r['field_source_urls']['kami_verbatim']=url
    m=re.search(r'<h2\b[^>]*\bid="map"[^>]*>.*?</h2>(.*?)(?=<h2\b|<!-- /#main)',ds,re.S|re.I)
    if m:
     q=Page(m[1]);ps=list(q.root.nodes('p'));a=next((x.text() for x in ps if '住所' in x.text() or re.search(r'(?:沖縄県)?那覇市',x.text())),None)
     if a:
      a=re.sub(r'^'+re.escape(name)+r'\s*住所[：:]\s*','',a)
      if name=='世持神社':a='波上宮内　沖縄県那覇市若狭1-25-11'
      r['address']=a;r['field_source_urls']['address']=url
    r['source_sha256']=sha(ds)
   except Exception as e:err.append({'url':url,'error':str(e)})
  rows.append(r)
 extra={'波上宮':'http://naminouegu.jp/yuisyo.html','宮古神社':'http://miyako-jinja.com/about.html','識名宮':'http://sikinagu.com/a.html'}
 for r in rows:
  if r['name'] not in extra:continue
  url=extra[r['name']]
  try:
   ds=fetch(url);pg=Page(ds);txt=pg.root.text();raw=None
   if r['name']=='宮古神社':
    raw='熊野三神 ・'+txt.split('熊野三神 ・',1)[1].split('宮古神社について')[0]
    r['address']=re.search(r'鎮座地 (.*?) 宮古神社 由緒',txt)[1];r['field_source_urls']['address']=url
   else:
    for m in re.finditer(r'<h2\b[^>]*>(.*?)</h2>(.*?)(?=<h2\b|$)',ds,re.S|re.I):
     if Page(m[1]).root.text() in ['御祭神','識名宮の御祭神']:raw=Page(m[2]).root.text();break
   if raw:r.update(kami_verbatim=raw,profile_url=url,source_sha256=sha(ds));r['field_source_urls']['kami_verbatim']=url
  except Exception as e:err.append({'url':url,'error':str(e)})
 assert len(rows)==10,len(rows)
 result(47,'沖縄県','沖縄県神社庁',[u],'All ten explicitly affiliated shrines in the published agency list; nine sourced deity sections from six agency profiles and three linked shrine-owned sites. Other Okinawa shrines outside this list are outside scope. Actual profile shrine addresses supersede directory office/contact addresses where explicitly distinguished. Map viewport centers are not shrine coordinates.',rows,err,not err,10)


def shimane_profiles():
 p=ROOT/'32-島根県.json';d=json.loads(p.read_text());rows=d['records'];fail=[];done=0
 fields={};urls=list(dict.fromkeys(r['profile_url'] for r in rows))
 with ThreadPoolExecutor(max_workers=16) as pool:
  fs={pool.submit(fetch,u):u for u in urls}
  for f in as_completed(fs):
   u=fs[f]
   try:
    s=f.result();pg=Page(s);fld={};lastkey=None
    for tr in pg.root.nodes('tr'):
     cs=[c for c in tr.children if isinstance(c,Node) and c.tag in ('td','th')]
     if len(cs)!=2:continue
     key=cs[0].text();value=cs[1].text()
     if key=='ふりがな' and lastkey=='神社名（正称)':fld['kana']=value or None
     if key=='神社コード':fld['directory_code']=value or None
     lastkey=key
    fld['profile_sha256']=hashlib.sha256(s.encode()).hexdigest();fields[u]=fld
   except Exception as e:fail.append({'url':u,'error':str(e)})
   done+=1
   if done%100==0 or done==len(urls):
    progress={'code':'32','processed':done,'total':len(urls),'profile_failures':len(fail)}
    (ROOT/'shimane-profile-progress.json').write_text(json.dumps(progress));print(json.dumps(progress),flush=True)
 for r in rows:
  fld=fields.get(r['profile_url'])
  if fld:
   r['kana']=fld.get('kana');r['directory_code']=fld.get('directory_code');r['profile_sha256']=fld['profile_sha256'];r['field_source_urls']['kana']=r['profile_url'] if r['kana'] else None
 # Keep original field/hash provenance for municipal table facts; add only independently observed profile facts.
 d['detail_completion']={'listed_profiles':len(urls),'fetched_profiles':len(fields),'failed_profiles':len(fail),'complete':not fail}
 d['failures']+=fail;d['scope_note']+=' All observed linked factual profiles were also requested for published shrine kana and directory code; original table name/deity/address fields are preserved with their own source hashes. Sampled profiles did not publish explicit map coordinates.'
 tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2));tmp.replace(p);print('FINAL',len(rows),sum(bool(r['kana']) for r in rows),len(fail),flush=True)

if __name__=='__main__':
 jobs={'32':shimane,'32-profiles':shimane_profiles,'40':fukuoka,'41':saga,'42':nagasaki,'47':okinawa}
 for code in (sys.argv[2:] or ['32','32-profiles','40','41','42','47']):jobs[code]()
