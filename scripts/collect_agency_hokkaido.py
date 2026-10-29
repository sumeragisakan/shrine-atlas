#!/usr/bin/env python3
"""Read all publicly linked Hokkaido Jinjacho branch pages and profiles."""
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urljoin,urlsplit,unquote
from concurrent.futures import ThreadPoolExecutor,as_completed
from collect_tottori import Page,Node
import hashlib,json,re,sys,threading,time

BASE='https://hokkaidojinjacho.jp/'
class Fetcher:
    def __init__(self,folder):self.folder=folder;folder.mkdir(parents=True,exist_ok=True);self.lock=threading.Lock();self.last=0
    def fetch(self,url):
        path=self.folder/(hashlib.sha256(url.encode()).hexdigest()+'.html')
        if path.exists():return path.read_text()
        for attempt in range(3):
            with self.lock:
                wait=.4-(time.monotonic()-self.last)
                if wait>0:time.sleep(wait)
                self.last=time.monotonic()
            try:
                with urlopen(Request(url,headers={'User-Agent':'ShrineAtlasResearch/0.5 (+https://github.com/sumeragisakan/shrine-atlas)'}),timeout=25)as r:text=r.read().decode('utf-8')
                path.write_text(text);return text
            except Exception as e:
                if getattr(e,'code',None)in(401,403,404)or attempt==2:raise
                time.sleep(attempt+1)

def profile(text,row):
    page=Page(text);fields={}
    for dl in page.root.nodes('dl'):
        for i,n in enumerate(dl.children):
            if isinstance(n,Node)and n.tag=='dt':
                dd=next((v for v in dl.children[i+1:]if isinstance(v,Node)and v.tag in('dt','dd')),None)
                if dd and dd.tag=='dd':fields[n.text()]=dd
    address=''
    if '所在地'in fields:
        dd=fields['所在地'];lines=[v.strip()for v in dd.raw().splitlines()if v.strip()]
        address=next((x for x in lines if re.search(r'[市郡町村区]',x)and not re.fullmatch(r'[0-9\-ー ]+',x)),'')
    points=[]
    for iframe in page.root.nodes('iframe'):
        url=iframe.attrs.get('src','')
        for m in re.finditer(r'(?:[?&](?:q|ll|query)=)(-?\d+\.\d+),(-?\d+\.\d+)',url):points.append((float(m[1]),float(m[2]),url))
    titles=[n.text()for n in page.root.nodes('title')]
    name=titles[0].split(' - ')[0]if titles else row['name']
    return {**row,'name':name,'address':address or row.get('address',''),'kana':'','kami_verbatim':fields['祭神'].raw().strip()if'祭神'in fields else None,
        'rank':fields['旧社格'].text()if'旧社格'in fields else None,'lat':points[0][0]if points else None,'lon':points[0][1]if points else None,
        'coordinate_source_url':row['profile_url']if points else None,'source_sha256':hashlib.sha256(text.encode()).hexdigest()}

def main():
    folder=Path(sys.argv[1]).resolve();fetcher=Fetcher(folder/'raw');home=Page(fetcher.fetch(urljoin(BASE,'jinja/')))
    branches={urljoin(BASE,a.attrs['href']):a.text()for a in home.root.nodes('a')if '/jinja-area/'in a.attrs.get('href','')}
    if len(branches)!=15:raise ValueError('Expected 15 public branches')
    pending=set(branches);seen=set();records={};failures=[];indexes=[]
    with ThreadPoolExecutor(max_workers=6)as pool:
        while pending:
            batch=sorted(pending-seen);pending.clear()
            if not batch:break
            tasks={pool.submit(fetcher.fetch,u):u for u in batch}
            for future in as_completed(tasks):
                u=tasks[future];seen.add(u)
                try:
                    text=future.result();page=Page(text)
                    label=next((v for k,v in branches.items()if u.startswith(k)),'北海道');indexes.append({'url':u,'label':label})
                    for a in page.root.nodes('a'):
                        href=urljoin(u,a.attrs.get('href',''));name=a.text();parts=urlsplit(href)
                        if '/jinja-area/'in parts.path and '/page/'in parts.path and href not in seen:pending.add(href)
                        if parts.netloc=='hokkaidojinjacho.jp'and len(parts.path.strip('/').split('/'))==1 and re.search(r'[一-龯ぁ-ゖァ-ヺ]',unquote(parts.path))and name:
                            records.setdefault(href,{'source_id':hashlib.sha256(href.encode()).hexdigest()[:16],'name':name,'address':'','address_legacy':None,'profile_url':href,'index_url':u,'branch':label})
                except Exception as e:failures.append({'url':u,'error':str(e)})
            print(json.dumps({'indexes':len(seen),'profiles_discovered':len(records),'pending_indexes':len(pending)}),flush=True)
        result=[];tasks={pool.submit(fetcher.fetch,u):r for u,r in records.items()}
        for future in as_completed(tasks):
            r=tasks[future]
            try:result.append(profile(future.result(),r))
            except Exception as e:failures.append({'url':r['profile_url'],'error':str(e)});result.append({**r,'kami_verbatim':None,'rank':None,'lat':None,'lon':None,'coordinate_source_url':None,'source_sha256':None})
            if len(result)%50==0:print(json.dumps({'profiles':len(result),'total':len(records),'failures':len(failures)}),flush=True)
    output={'code':1,'name':'北海道','provider':'北海道神社庁','label':'北海道神社庁・15支部公开名录','index_urls':[x['url']for x in indexes],
        'scope_note':'覆盖网站公开链接的15支部名录及其全部可访问详情，不等于县内全部小祠或未列名设施。地址查询地图不转换为估算坐标。',
        'expected_rows':len(records),'pagination_complete':not any('jinja-area'in f['url']for f in failures),'records':sorted(result,key=lambda r:r['profile_url']),'failures':failures}
    path=folder/'01-hokkaido.json';path.write_text(json.dumps(output,ensure_ascii=False,separators=(',',':'))+'\n')
    print(json.dumps({'output':str(path),'records':len(result),'mapped':sum(r['lat']is not None for r in result),'failures':len(failures)}),flush=True)

if __name__=='__main__':main()
