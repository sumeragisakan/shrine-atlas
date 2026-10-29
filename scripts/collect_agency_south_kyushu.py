#!/usr/bin/env python3
"""Cache primary southern Kyushu public shrine-directory facts. No publication."""
from __future__ import annotations
import hashlib,json,re,runpy,sys,threading,time,urllib.request,urllib.error
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
from urllib.parse import urljoin,urlsplit,urlencode
REPO=Path(__file__).resolve().parents[1];ROOT=REPO.parent
OUT=ROOT/'national-research/agency-west/south-kyushu';CACHE=OUT/'cache'; CACHE.mkdir(parents=True,exist_ok=True)
SHARED=ROOT/'national-research/agency-west/cache'
mod=runpy.run_path(str(REPO/'scripts/collect_tottori.py'));Page=mod['Page'];Node=mod['Node']
LOCK=threading.Lock();LAST={}

def fetch(url):
 f=CACHE/(hashlib.sha256(url.encode()).hexdigest()+'.html');mf=f.with_suffix('.meta.json')
 if f.exists() and ('wp-json/wp/v2/posts?' not in url or mf.exists()):return f.read_text(),json.loads(mf.read_text()) if mf.exists() else {}
 older=SHARED/f.name
 if older.exists():s=older.read_text();f.write_text(s);return s,{}
 host=urlsplit(url).netloc;err=None
 for attempt in range(3):
  with LOCK:
   delay=.3-(time.monotonic()-LAST.get(host,0))
   if delay>0:time.sleep(delay)
   LAST[host]=time.monotonic()
  try:
   req=urllib.request.Request(url,headers={'User-Agent':'ShrineAtlasResearch/0.3 (+https://github.com/sumeragisakan/shrine-atlas)'})
   with urllib.request.urlopen(req,timeout=30) as r:b=r.read();enc=r.headers.get_content_charset();meta={k.lower():v for k,v in r.headers.items() if k.lower() in ['x-wp-total','x-wp-totalpages','content-type']}
   if not enc:
    m=re.search(br'charset=["\']?([\w-]+)',b[:5000]);enc=m[1].decode() if m else 'utf-8'
   s=b.decode(enc,errors='replace');f.write_text(s);mf.write_text(json.dumps(meta));return s,meta
  except Exception as e:
   err=e
   if isinstance(e,urllib.error.HTTPError) and e.code in [401,403,404]:break
   if attempt<2:time.sleep(1+attempt)
 raise RuntimeError(f'{url}: {err}')

def cls(n,c):return c in n.attrs.get('class','').split()
def direct(n,t=None):return [x for x in n.children if isinstance(x,Node) and (not t or x.tag==t)]
def find(n,t,c=None):return [x for x in n.nodes(t) if c is None or cls(x,c)]
def txt(n):return n.text().strip() if n else None
def raw(n):return re.sub(r'[ \t]+',' ',n.raw()).strip() if n else None
def blank(x):return x if x and x.strip() else None
def base_rec(name,url,idx,sha):return dict(source_id=url,name=name,kana=None,address=None,address_legacy=None,kami_verbatim=None,rank=None,profile_url=url,index_url=idx,lat=None,lon=None,coordinate_source_url=None,source_sha256=sha,field_source_urls={'name':idx,'kana':None,'address':None,'kami_verbatim':None,'rank':None,'lat':None,'lon':None})
def save(code,name,provider,label,indexes,note,expected,complete,records,failures):
 data=dict(code=code,name=name,provider=provider,label=label,index_urls=sorted(set(indexes)),scope_note=note,expected_rows=expected,pagination_complete=complete,records=sorted(records,key=lambda x:x['source_id']),failures=failures)
 f=OUT/(str(code)+'.json');f.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')))
 print(json.dumps(dict(code=code,rows=len(records),deities=sum(bool(x['kami_verbatim']) for x in records),addresses=sum(bool(x['address']) for x in records),complete=complete,failures=len(failures)),ensure_ascii=False),flush=True)
 return data

def crawl_indexes(start,pattern,parser):
 todo=set(start);seen=set();records={};fails=[]
 with ThreadPoolExecutor(max_workers=8) as pool:
  while todo:
   batch=sorted(todo-seen);todo=set();seen.update(batch)
   fs={pool.submit(fetch,u):u for u in batch}
   for future in as_completed(fs):
    u=fs[future]
    try:
     s,_=future.result();p=Page(s);rs=parser(p,u,hashlib.sha256(s.encode()).hexdigest())
     for r in rs: records[r['source_id']]=r
     for a in p.root.nodes('a'):
      v=urljoin(u,a.attrs.get('href','')).split('#')[0]
      if re.fullmatch(pattern,v) and v not in seen:todo.add(v)
    except Exception as e:fails.append({'url':u,'error':str(e)})
   print(json.dumps({'indexes':len(seen),'rows':len(records),'pending':len(todo),'failures':len(fails)}),flush=True)
 return list(records.values()),sorted(seen),fails

def miyazaki_list(p,u,sha):
 rows=[]
 for ul in find(p.root,'ul','shrine_list'):
  for li in direct(ul,'li'):
   hs=list(li.nodes('h2'));links=[a for a in li.nodes('a') if '/m_shrine/' in a.attrs.get('href','')]
   if not hs or len(links)!=1:continue
   name=hs[0].text();kana=None;qualifier=None;m=re.fullmatch(r'(.*?)[（(]([^（）()]+)[）)](.*)',name)
   if m:name,kana,qualifier=m.groups()
   r=base_rec(name.strip(),urljoin(u,links[0].attrs['href']),u,sha);r['kana']=kana
   if qualifier and qualifier.strip():r['name_qualifier']=qualifier.strip()
   if kana:r['field_source_urls']['kana']=u
   for box in find(li,'div','data_list'):
    children=direct(box,'div')
    if len(children)==2 and children[0].text()=='住所':
     r['address']=blank(children[1].text())
     if r['address']:r['field_source_urls']['address']=u
   rows.append(r)
 return rows

def miyazaki_details(r):
 s,_=fetch(r['profile_url']);p=Page(s)
 for box in find(p.root,'div','data_list'):
  ch=direct(box,'div')
  if len(ch)!=2:continue
  key=ch[0].text()
  if key=='御祭神':r['kami_verbatim']=blank(raw(ch[1]))
  if key=='旧社格':r['rank']=blank(ch[1].text())
  if key=='住所':r['address']=blank(ch[1].text())
  field={'御祭神':'kami_verbatim','旧社格':'rank','住所':'address'}.get(key)
  if field and r[field]:r['field_source_urls'][field]=r['profile_url']
 # The source labels one deity string as an address and the street address as a postal code.
 # Preserve the published labels separately; do not silently remap these fields.
 if r['address']=='火産霊神（ほむすびのかみ）':
  anomalies=[]
  for box in find(p.root,'div','data_list'):
   ch=direct(box,'div')
   if len(ch)==2 and ch[0].text() in ['住所','郵便番号']:
    anomalies.append({'label':ch[0].text(),'value':ch[1].text(),'source_url':r['profile_url']})
  r['source_field_anomalies']=anomalies;r['address']=None;r['field_source_urls']['address']=None
 r['source_sha256']=hashlib.sha256(s.encode()).hexdigest()
 return r

def run45():
 rows,indexes,fails=crawl_indexes(['https://www.m-shinsei.jp/shrine/'],r'https://www\.m-shinsei\.jp/shrine/(?:page/\d+/)?',miyazaki_list)
 note='宮崎県神道青年会が公開する宮巡の全一覧ページ。サイトは649社の検索を案内。公開一覧の収録範囲であり、県内のすべての実在する祠・境内社までの網羅性を保証しない。神名は御祭神欄を原文で保持。小國神社の原ページでは住所と郵便番号欄に内容のずれが見られるため、その値をsource_field_anomaliesに保ち、住所・祭神を推測補完しない。'
 save(45,'宮崎県','宮崎県神道青年会','宮巡 神社一覧',indexes,note,649,not fails,rows,fails)
 with ThreadPoolExecutor(max_workers=8) as pool:
  fs={pool.submit(miyazaki_details,r):r for r in rows}
  for n,f in enumerate(as_completed(fs),1):
   try:f.result()
   except Exception as e:fails.append({'url':fs[f]['profile_url'],'error':str(e)})
   if n%100==0 or n==len(fs):
    save(45,'宮崎県','宮崎県神道青年会','宮巡 神社一覧',indexes,note,649,not fails,rows,fails)

def kumamoto_list(p,u,sha):
 rows=[]
 for tr in p.root.nodes('tr'):
  cells=[x for x in direct(tr) if x.tag in ['th','td']]
  links=[a for a in tr.nodes('a') if '/patron-god/' in a.attrs.get('href','')]
  if len(cells)<2 or len(links)!=1:continue
  r=base_rec(cells[0].text(),urljoin(u,links[0].attrs['href']),u,sha)
  r['listed_region']=blank(cells[1].text());r['listed_region_source_url']=u;rows.append(r)
 return rows

def run43():
 rows,indexes,fails=crawl_indexes(['https://kumamotokenjinjacho.jp/patron-god/'],r'https://kumamotokenjinjacho\.jp/patron-god/(?:page/\d+/)?',kumamoto_list)
 note='熊本県神社庁の氏神様検索の全公開一覧ページ。サイトは人吉・球磨地方のみ試験運用中・順次更新と明記するが、現公開一覧には他地域の結果もある。お住まいの地域欄は氏子区域等を含み得るためlisted_regionに保持し、神社所在地addressには転記しない。県内全神社を網羅しない。'
 save(43,'熊本県','熊本県神社庁','氏神様を探す',indexes,note,None,not fails,rows,fails)

def kago_record(post,u,sha):
 p=Page(post['content']['rendered']);r=base_rec(Page(post['title']['rendered']).root.text(),post['link'],'https://www.kagojinjacho.or.jp/search/',sha)
 r['source_id']=str(post['id'])
 for li in p.root.nodes('li'):
  t=li.text();m=re.match(r'^(神社名|神社名カナ|鎮座地|旧社格)[：:]\s*(.*)$',t)
  if not m:continue
  key,val=m.groups();field={'神社名':'name','神社名カナ':'kana','鎮座地':'address','旧社格':'rank'}[key];r[field]=blank(val)
 def walk(n):
  for x in n.children:
   if isinstance(x,Node):
    yield x
    yield from walk(x)
 flat=list(walk(p.root))
 for at,h in enumerate(flat):
  if h.tag=='h4' and h.text()=='御祭神':
   for x in flat[at+1:]:
    if x.tag=='h4':break
    if cls(x,'templeMain'):
     r['kami_verbatim']=blank(raw(x));break
 # The API response is a primary public endpoint; profile URL points to matching visible source.
 r['api_source_url']=u
 for field in ['name','kana','address','kami_verbatim','rank']:
  r['field_source_urls'][field]=u if r[field] else None
 return r

def run46():
 root='https://www.kagojinjacho.or.jp/wp-json/';api=json.loads(fetch(root)[0]);route=api['routes']['/wp/v2/posts']['_links']['self'];params={'per_page':100,'page':1};first=route+'?'+urlencode(params);s,meta=fetch(first);posts=json.loads(s);pages=int(meta.get('x-wp-totalpages',0));failures=[];sources=[first]
 if not pages:raise RuntimeError('Missing API pagination-total header; refuse to assume completion')
 rs=[]
 for post in posts:
  if '/shrine-search/' in post.get('link',''):rs.append(kago_record(post,first,hashlib.sha256(s.encode()).hexdigest()))
 with ThreadPoolExecutor(max_workers=8) as pool:
  fs={pool.submit(fetch,route+'?'+urlencode({'per_page':100,'page':i})):route+'?'+urlencode({'per_page':100,'page':i}) for i in range(2,pages+1)}
  for f in as_completed(fs):
   u=fs[f];sources.append(u)
   try:
    s,_=f.result()
    for post in json.loads(s):
     if '/shrine-search/' in post.get('link',''):rs.append(kago_record(post,u,hashlib.sha256(s.encode()).hexdigest()))
   except Exception as e:failures.append({'url':u,'error':str(e)})
 note='鹿児島県神社庁の神社を探すに掲載された7地区の神社を、サイトが公開するWordPress APIの全ページから収集。地区件数合計1104件と照合。公開ディレクトリの収録範囲であり全実在祠の網羅を意味しない。御祭神は公開本文の該当欄原文。'
 save(46,'鹿児島県','鹿児島県神社庁','神社を探す', ['https://www.kagojinjacho.or.jp/search/']+sources,note,1104,not failures and len(rs)==1104,rs,failures)

def run44():
 note='神社本庁の神社庁一覧と岡山県神社庁公式リンク一覧を確認したが、大分県神社庁の公開神社ディレクトリは発見できなかった。このファイルは現行公式庁ディレクトリ補足の欠落を明示するものであり、親収集の全国神社検索の歴史的補助データを置換しない。'
 save(44,'大分県','神社本庁・岡山県神社庁','現行神社庁ディレクトリ未発見',['https://www.jinjahoncho.or.jp/jinjahoncho/jinjacho/','https://www.okayama-jinjacho.or.jp/link/'],note,None,False,[],[{'type':'no_public_directory_found','error':'Primary prefectural-agency directory not found after primary-source link checks.'}])
if __name__=='__main__':
 codes=sys.argv[1:] or ['43','44','45','46']
 for code in codes:
  try:globals()['run'+code]()
  except Exception as e:print('FATAL',code,str(e),flush=True)
