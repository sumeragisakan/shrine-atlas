#!/usr/bin/env python3
"""Collect the public research-group directory, retaining its historical scope.

Raw responses stay outside Git. Facts come from each prefecture's public POST
search results, not from guessed IDs or assumed present-day shrine details.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode, urljoin
from urllib.error import HTTPError
import hashlib
import json
import re
import sys
import threading
import time

from collect_tottori import Page, Node

HOME='https://jinja-net.jp/jinja-all/index.html'
DATE='2026-10-30'
UA='ShrineAtlasResearch/0.5 (+https://github.com/sumeragisakan/shrine-atlas)'


class Fetcher:
    def __init__(self,folder):
        self.folder=folder;folder.mkdir(parents=True,exist_ok=True)
        self.lock=threading.Lock();self.last=0
    def fetch(self,url,name,data=None):
        path=self.folder/name
        if path.exists():return path.read_text()
        for attempt in range(3):
            with self.lock:
                delay=1-(time.monotonic()-self.last)
                if delay>0:time.sleep(delay)
                self.last=time.monotonic()
            try:
                request=Request(url,data=data,headers={'User-Agent':UA})
                with urlopen(request,timeout=35)as response:
                    raw=response.read();encoding=response.headers.get_content_charset()or'utf-8'
                text=raw.decode(encoding);path.write_text(text);return text
            except HTTPError as e:
                if e.code in (401,403,404):raise
                if e.code==429:
                    delay=int(e.headers.get('Retry-After','15'))
                    if delay>60:raise
                    time.sleep(delay)
                if attempt==2:raise
            except Exception:
                if attempt==2:raise
            time.sleep(1+attempt)


def parse_results(text,code,name,url):
    page=Page(text);rows=[]
    count=re.search(r'検索結果\s*([\d,]+)\s*件',page.root.text())
    if not count:raise ValueError('No published result count')
    for tr in page.root.nodes('tr'):
        if 'result-row' not in tr.attrs.get('class','').split():continue
        cells=[c for c in tr.children if isinstance(c,Node)and c.tag=='td']
        if len(cells)<5:raise ValueError('Unexpected result columns')
        ident=tr.attrs.get('data-id')
        if not ident or not ident.isdigit():raise ValueError('No observed result ID')
        button=next((n for n in tr.nodes('input')if n.attrs.get('onclick')==f'showDetail({ident})'),None)
        if button is None:raise ValueError('No observed detail action')
        addresses=[v.strip() for v in cells[3].raw().splitlines() if v.strip()]
        current=addresses[0]if addresses else ''
        legacy=' '.join(addresses[1:])if len(addresses)>1 else ''
        # A prefecture-only current column is a placeholder, not a street address.
        if current in (name,name+'県',name+'府',name+'都',name+'道'):current=''
        rows.append({'source_id':ident,'name':tr.attrs.get('data-name')or cells[2].text(),
            'kana':'','address':current,'address_legacy':legacy,'kami_verbatim':cells[4].raw().strip(),
            'profile_url':urljoin(url,'jsearch3all.php?jinjya='+ident),'profile_fetched':False,
            'index_url':url,'source_row_sha256':hashlib.sha256(str(tr.attrs).encode()+tr.raw().encode()).hexdigest()})
    expected=int(count[1].replace(',',''))
    if len(rows)!=expected:raise ValueError(f'Published {expected}, extracted {len(rows)}')
    if len({r['source_id']for r in rows})!=len(rows):raise ValueError('Duplicate source IDs within query')
    return {'code':code,'name':name,'provider':'神社史研究会・新全国神社検索',
        'source_home':HOME,'query_url':url,'request':{'method':'POST','parameters':{'data_item':'shibu','data_choice':str(code)}},
        'checked':DATE,'expected_rows':expected,'pagination_complete':True,'source_sha256':hashlib.sha256(text.encode()).hexdigest(),
        'scope_note':'该研究会公开检索的地区结果；包括平成5年（1993）调查与合并前旧地址，不能当作现今全数名录或现址确认。',
        'records':rows,'failures':[]}


def main():
    folder=Path(sys.argv[1]).resolve();fetcher=Fetcher(folder)
    bootstrap=folder.parent/'jinja-net-index.html'
    text=bootstrap.read_text()if bootstrap.exists()else fetcher.fetch(HOME,'index.html')
    page=Page(text);form=next(f for f in page.root.nodes('form')if f.attrs.get('id')=='formKensaku')
    endpoint=urljoin(HOME,form.attrs['action'])
    choices=[(int(n.attrs['name']),n.attrs['value'])for n in form.nodes('input')if n.attrs.get('class')=='shibu_submit']
    if {c for c,n in choices}!=set(range(1,48)):raise ValueError('Expected 47 observed prefecture choices')
    results=[];failures=[]
    def collect(choice):
        code,name=choice;payload=urlencode({'data_item':'shibu','data_choice':str(code),'searchterm':'','meisyo':''}).encode()
        text=fetcher.fetch(endpoint,f'pref-{code:02d}.html',payload)
        result=parse_results(text,code,name,endpoint)
        (folder/f'pref-{code:02d}.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n')
        return result
    with ThreadPoolExecutor(max_workers=4)as pool:
        tasks={pool.submit(collect,c):c for c in choices}
        for future in as_completed(tasks):
            code,name=tasks[future]
            try:
                result=future.result();results.append({k:v for k,v in result.items()if k!='records'})
                print(json.dumps({'prefecture':code,'name':name,'records':result['expected_rows']},ensure_ascii=False),flush=True)
            except Exception as e:
                failures.append({'code':code,'name':name,'error':str(e)})
                print(json.dumps(failures[-1],ensure_ascii=False),flush=True)
    summary={'checked':DATE,'prefectures':sorted(results,key=lambda r:r['code']),'failures':failures}
    (folder/'manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'prefectures':len(results),'records':sum(r['expected_rows']for r in results),'failures':len(failures)}),flush=True)
    if failures:raise SystemExit(1)

if __name__=='__main__':main()
