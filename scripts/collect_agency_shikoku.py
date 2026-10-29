#!/usr/bin/env python3
"""Public Shikoku prefectural shrine-directory research only; cached raw pages remain private."""
import runpy,urllib.request,urllib.error,json,re,hashlib,time,threading,sys
from pathlib import Path
from urllib.parse import urljoin,urlsplit,quote
from concurrent.futures import ThreadPoolExecutor,as_completed
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'national-research/agency-west/shikoku'; CACHE=OUT/'cache'; CACHE.mkdir(parents=True,exist_ok=True)
PARSER=runpy.run_path(str(ROOT/'shrine-atlas/scripts/collect_tottori.py'));Page=PARSER['Page'];Node=PARSER['Node']
locks={};last={};glob=threading.Lock()
def fetch(url):
 key=hashlib.sha256(url.encode()).hexdigest(); p=CACHE/(key+'.html')
 for q in [p,ROOT/'national-research/agency-west/cache'/(key+'.html')]:
  if q.exists():return q.read_text()
 host=urlsplit(url).netloc
 with glob:lock=locks.setdefault(host,threading.Lock())
 with lock:
  pause=.35-(time.monotonic()-last.get(host,0))
  if pause>0:time.sleep(pause)
  last[host]=time.monotonic()
 req=urllib.request.Request(url,headers={'User-Agent':'ShrineAtlasResearch/0.3 (+https://github.com/sumeragisakan/shrine-atlas)'})
 for attempt in range(2):
  try:
   with urllib.request.urlopen(req,timeout=30) as r:
    b=r.read();enc=r.headers.get_content_charset();headers=dict(r.headers)
   (CACHE/(key+'.headers.json')).write_text(json.dumps(headers))
   if not enc:
    m=re.search(br'charset=["\']?([\w-]+)',b[:5000]);enc=m[1].decode() if m else 'utf-8'
   try:s=b.decode(enc)
   except (LookupError,UnicodeDecodeError):s=b.decode('utf-8','replace')
   p.write_text(s);(CACHE/(key+'.url')).write_text(url)
   return s
  except urllib.error.HTTPError as e:
   if e.code in [400,401,403,404] or attempt:raise
  except Exception:
   if attempt:raise
  time.sleep(1)
def batch(urls,workers=5):
 result={};fail={}
 with ThreadPoolExecutor(max_workers=workers) as pool:
  fs={pool.submit(fetch,u):u for u in dict.fromkeys(urls)}
  for i,f in enumerate(as_completed(fs),1):
   u=fs[f]
   try:result[u]=f.result()
   except Exception as e:fail[u]=str(e)
   if i%25==0 or i==len(fs):print(json.dumps({'done':i,'total':len(fs),'failures':len(fail)}),flush=True)
 return result,fail
def attrs(n,c):return c in n.attrs.get('class','').split()
def tagtext(n):return n.raw().strip()
def rec(source_id,name,url,index,s,**kw):
 d={'source_id':str(source_id),'name':name,'kana':None,'address':None,'address_legacy':None,'kami_verbatim':None,'rank':None,'profile_url':url,'index_url':index,'lat':None,'lon':None,'coordinate_source_url':None,'source_sha256':hashlib.sha256(s.encode()).hexdigest()};d.update(kw);d['field_source_urls']={f:(d.get('coordinate_source_url') if f in ['lat','lon'] else url) if d.get(f) is not None else None for f in ['name','kana','address','kami_verbatim','rank','lat','lon']};return d
def save(code,name,provider,indexes,note,records,failures,complete,expected=None,warnings=None):
 d={'code':str(code),'name':name,'provider':provider,'label':name+'神社庁公開神社案内','index_urls':indexes,'scope_note':note,'expected_rows':expected,'pagination_complete':complete,'records':records,'failures':failures}
 if warnings:d['warnings']=warnings
 (OUT/(str(code)+'-agency.json')).write_text(json.dumps(d,ensure_ascii=False,separators=(',',':')))
 print(json.dumps({'prefecture':code,'records':len(records),'deity':sum(bool(x['kami_verbatim']) for x in records),'coords':sum(x['lat'] is not None for x in records),'failures':len(failures),'complete':complete},ensure_ascii=False),flush=True)
def inspect():
 urls=['https://awa-jinjacho.jp/shrine/','https://kagawakenjinjacho.or.jp/wp-json/','https://kagawakenjinjacho.or.jp/shrine/%e8%97%b7_%e7%a4%be/','https://ehime-jinjacho.jp/jinja/?p=448','https://www.kochi-jinjyacho.com/']
 data,fail=batch(urls)
 for u,s in data.items():
  p=Page(s);print('URL',u,'TEXT',p.root.text()[:10000]); print('LINKS',[(a.text(),urljoin(u,a.attrs.get('href',''))) for a in p.root.nodes('a') if a.attrs.get('href')][:100])
 print('FAIL',fail)
def fields(s):
 p=Page(s);d={}
 for tr in p.root.nodes('tr'):
  cs=[c for c in tr.children if isinstance(c,Node) and c.tag in ['td','th']]
  if len(cs)==2:d[cs[0].text()]=tagtext(cs[1]) or None
 return d

def kagawa():
 base='https://kagawakenjinjacho.or.jp/wp-json/wp/v2/shrine'
 index='https://kagawakenjinjacho.or.jp/shrine/'
 api=[base+'?per_page=100&page='+str(n) for n in range(1,9)]
 data,fail=batch(api); entries=[]
 for u,s in data.items():entries+=json.loads(s)
 profiles={x['link']:x for x in entries}; pages,detailfail=batch(profiles,16);fail.update(detailfail);records=[]
 for url,x in sorted(profiles.items()):
  s=pages.get(url,'');p=Page(s);d={}
  for n in p.root.nodes('p'):
   cls=n.attrs.get('class','')
   if cls in ['shrine_code','shrine_name','location','enshrined_deity']:
    d[cls]=re.split('[：:]',tagtext(n),maxsplit=1)[-1].strip() or None
  records.append(rec(x['id'],d.get('shrine_name') or Page(x['title']['rendered']).root.text(),url,index,s,address=d.get('location'),kami_verbatim=d.get('enshrined_deity'),directory_code=d.get('shrine_code')))
 save('37','香川県','香川県神社庁',api,'公開神社一覧と、その公開詳細ページを収集。神社庁の掲載範囲であり、県内の全ての実在する神社の網羅性を意味しない。空欄の祭神はnull。住所は公開欄の転記で、現地の現況確認はしていない。神社コード9047は異なる2社に重複しているため、source_idには公開WordPressレコードIDを使用し、directory_codeに元のコードを保存。',records,fail,len(entries)==770 and not fail,770)

def ehime():
 index='https://ehime-jinjacho.jp/jinja/';s=fetch(index)
 pattern=r'var point = new google\.maps\.LatLng\(([^)]*)\);\s*var marker = create_maker\(point, "([^"]+)", \'<div><a href="([^"]+)"'
 rows=re.findall(pattern,s);profiles={u:(c,n) for c,n,u in rows}
 pages,fail=batch(profiles,16);records=[];warnings=[]
 for url,(coords,name) in sorted(profiles.items()):
  body=pages.get(url,'');d=fields(body);point=[None,None]
  if re.fullmatch(r'[-\d.]+,[-\d.]+',coords):point=list(map(float,coords.split(',')))
  records.append(rec(url.split('=')[-1],d.get('神社名') or name,url,index,body,kana=d.get('ふりがな'),address=d.get('神社鎮座地'),kami_verbatim=d.get('神社主祭神'),lat=point[0],lon=point[1],coordinate_source_url=index if point[0] is not None else None))
  if point[0] is not None and not (32<point[0]<35 and 131<point[1]<135):
   records[-1]['coordinate_quality']='outside_prefecture_review'
   warnings.append({'source_id':records[-1]['source_id'],'kind':'coordinate_outside_prefecture','message':'Published map coordinate is outside the prefecture bounding region; retained verbatim for review without geocoding or correction.','source_url':index})
 save('38','愛媛県','愛媛県神社庁',[index],'公開マップに掲載された1234件の神社詳細リンクを収集。掲載範囲を網羅し、全実在神社を保証しない。住所は公開欄の転記で、現地の現況確認はしていない。公開マップに空のLatLng値がある場合は座標null。公開座標が明らかに県外を指す場合はcoordinate_qualityで要確認とし、公開値を補正していない。',records,fail,not fail,len(profiles),warnings)

def partials():
 u='https://awa-jinjacho.jp/shrine/'
 save('36','徳島県','徳島県神社庁',[u],'公式神社庁の神社案内URLはHTTP/HTTPSとも503応答。現在の神社庁案内は取得できず、この収集の0件は実在神社の欠如を意味しない。',[],[{'url':u,'error':'HTTP 503 after two ordinary public fetch attempts'},{'url':'http://awa-jinjacho.jp/shrine/','error':'HTTP 503 after two ordinary public fetch attempts'}],False)
 u='https://www.kochi-jinjyacho.com/%E9%AB%98%E7%9F%A5%E7%9C%8C%E7%A5%9E%E7%A4%BE%E4%B8%80%E8%A6%A7'
 s=fetch(u);p=Page(s);records=[]
 warm=None
 for sc in p.root.nodes('script'):
  if sc.attrs.get('id')=='wix-warmup-data':warm=json.loads(''.join(x for x in sc.children if isinstance(x,str)))
 for h in list(p.root.nodes('h2'))[:26]:
  container=h.parent.parent;txt=container.text();match=re.search(r'(高知県.*?) (?:\u200b?電話|電話)',txt)
  name=h.text();sid=h.parent.attrs['id'];records.append(rec(sid,name,u,u,s,address=match[1].strip() if match else None))
 ds=warm['appsWarmupData']['dataBinding']['dataStore'];total=ds['recordInfosByDatasetId']['comp-ljqfjyd6']['datasetSize']['total']
 for sid,x in ds['recordsByCollectionId']['4gq343hu3awdp28flsx'].items():
  records.append(rec(sid,x.get('text'),u,u,s,address=(x.get('newField','')+x.get('text1','')) or None))
 save('39','高知県','高知県神社庁',[u],'公式一覧ページの注目神社26件と、公開HTMLに初期表示された検索結果12件を収集。検索データセットは4215行と表示されるが、残りのページは取得していない。公開サイトのクライアントに記された読取APIは通常の匿名要求に403応答したため、認証やアクセス回避を試みずに停止。この部分収集は全神社の網羅ではない。住所の現況確認はしていない。',records,[{'url':'https://www.kochi-jinjyacho.com/_serverless/data-binding-server/fetch-data','error':'Ordinary anonymous public-client read request returned HTTP 403; pagination not collected.'}],False,total)

if __name__=='__main__':
 {'inspect':inspect,'kagawa':kagawa,'ehime':ehime,'partials':partials}[sys.argv[1] if len(sys.argv)>1 else 'inspect']()
