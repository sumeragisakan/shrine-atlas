#!/usr/bin/env python3
"""Read the public Tottori Jinjacho directory, caching pages outside the repo.

Only the parsed research manifest is an intermediate output. Raw pages are not
published. Run `python scripts/import_tottori.py CACHE` after reviewing it.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
import hashlib
import json
import re
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from urllib.parse import urljoin

BASE='https://tottori-jinjacho.jp/'
ROOT=Path(__file__).resolve().parents[1]
VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}


@dataclass
class Node:
    tag: str
    attrs: dict=field(default_factory=dict)
    children: list=field(default_factory=list)
    parent: object=None

    def nodes(self,tag):
        for child in self.children:
            if isinstance(child,Node):
                if child.tag==tag:yield child
                yield from child.nodes(tag)

    def raw(self):
        if self.tag in ('script','style'):return ''
        out=''.join(c.raw() if isinstance(c,Node) else c for c in self.children)
        return out+ ('\n' if self.tag in ('div','p','br','li','tr','h1','h2','h3') else '')

    def text(self):
        return re.sub(r'\s+',' ',self.raw()).strip()


class Page(HTMLParser):
    def __init__(self,html):
        super().__init__(convert_charrefs=True)
        self.root=Node('root');self.current=self.root
        self.feed(html)

    def handle_starttag(self,tag,attrs):
        node=Node(tag,dict(attrs),parent=self.current)
        self.current.children.append(node)
        if tag not in VOID:self.current=node

    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag not in VOID:self.handle_endtag(tag)

    def handle_endtag(self,tag):
        node=self.current
        while node is not self.root:
            if node.tag==tag:
                self.current=node.parent;return
            node=node.parent

    def handle_data(self,text):
        self.current.children.append(text)


def normalize(text):
    return unicodedata.normalize('NFKC',text).strip()


def index_rows(html,index):
    page=Page(html);rows=[]
    for tr in page.root.nodes('tr'):
        cells=[c for c in tr.children if isinstance(c,Node) and c.tag in ('th','td')]
        if len(cells)<3 or not re.fullmatch(r'\d{1,4}',normalize(cells[0].text())):continue
        links=list({urljoin(BASE,a.attrs['href']):a for a in cells[1].nodes('a')
                    if re.search(r'/pages/\d+/',a.attrs.get('href',''))}.values())
        if len(links)>1:raise ValueError('Ambiguous directory row: '+tr.text())
        link=links[0] if links else None
        rows.append({'number':int(normalize(cells[0].text())),
            'name':cells[1].text(),'listed_address':cells[2].text(),
            'url':urljoin(BASE,link.attrs['href']) if link else None,
            'index_url':index['url'],'index_label':index['label']})
    return rows


FIELDS={'神社名','よみ','住所','電話','祭神','御祭神','祭祀','旧社格','各種指定','その他'}


def detail_fields(html):
    page=Page(html);fields={}
    for tr in page.root.nodes('tr'):
        cells=[c for c in tr.children if isinstance(c,Node) and c.tag in ('th','td')]
        if len(cells)!=2:continue
        key=re.sub(r'\s+','',cells[0].text())
        if key in FIELDS:
            fields[key]=cells[1].raw().strip()
    history=[]
    for heading in page.root.nodes('h3'):
        if heading.text()=='由緒':
            section=heading.parent
            history.append(section.text().removeprefix('由緒').strip())
    points=[]
    for match in re.finditer(r'(?:\?|&|&amp;)q=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)',html):
        point=[float(match[1]),float(match[2])]
        if point not in points:points.append(point)
    return {'fields':fields,'history':' '.join(history), 'points':points,
            'html_sha256':hashlib.sha256(html.encode()).hexdigest()}


class Fetcher:
    def __init__(self,cache):
        self.cache=cache;cache.mkdir(parents=True,exist_ok=True)
        self.lock=threading.Lock();self.last=0.0

    def fetch(self,url):
        key=re.search(r'/pages/(\d+)/',url)
        name='page-'+key[1]+'.html' if key else 'home.html'
        path=self.cache/name
        if path.exists():return path.read_text(encoding='utf-8')
        error=None
        for attempt in range(3):
            with self.lock:
                pause=.3-(time.monotonic()-self.last)
                if pause>0:time.sleep(pause)
                self.last=time.monotonic()
            try:
                request=urllib.request.Request(url,headers={'User-Agent':'ShrineAtlasResearch/0.3 (+https://github.com/sumeragisakan/shrine-atlas)'})
                with urllib.request.urlopen(request,timeout=20) as response:
                    html=response.read().decode('utf-8')
                if len(html)<1000:raise ValueError('Unexpectedly short source page')
                path.write_text(html,encoding='utf-8')
                return html
            except urllib.error.HTTPError as exc:
                error=exc
                if exc.code in (401,403,404):break
                if exc.code==429:
                    delay=int(exc.headers.get('Retry-After','15'))
                    if delay>60:break
                    time.sleep(delay)
            except Exception as exc:error=exc
            if attempt<2:time.sleep(attempt+1)
        raise RuntimeError(f'{url}: {error}')


def main():
    cache=Path(sys.argv[1]).resolve()
    workers=max(1,min(16,int(sys.argv[2]) if len(sys.argv)>2 else 6))
    fetcher=Fetcher(cache)
    # Public non-query directory pages are allowed by the site's robots rules.
    home=Page(fetcher.fetch(BASE));indexes=[];seen=set()
    for a in home.root.nodes('a'):
        label=a.text();url=urljoin(BASE,a.attrs.get('href',''))
        if re.fullmatch(r'(鳥取市[（(].+[）)]|米子市|倉吉市|境港市|岩美町|八頭町|若桜町|智頭町|三朝町|琴浦町|湯梨浜町|北栄町|日吉津村|大山町|南部町|伯耆町|江府町|日野町|日南町)',label) and url not in seen:
            seen.add(url);indexes.append({'label':label,'url':url})
    if len(indexes)!=22:raise ValueError(f'Expected 22 region directories, got {len(indexes)}')
    rows=[]
    with ThreadPoolExecutor(max_workers=min(3,workers)) as pool:
        futures={pool.submit(fetcher.fetch,i['url']):i for i in indexes}
        for f in as_completed(futures):
            index=futures[f];entries=index_rows(f.result(),index)
            if not entries:raise ValueError('Empty index '+str(index))
            index['entries']=len(entries);rows+=entries
            print(json.dumps({'index':index['label'],'entries':len(entries)},ensure_ascii=False),flush=True)
    rows.sort(key=lambda r:r['number'])
    (cache/'index-manifest.json').write_text(json.dumps({'indexes':indexes,'rows':rows},ensure_ascii=False,indent=2))
    urls=sorted({r['url'] for r in rows if r['url']})
    details={};failures={}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(fetcher.fetch,url):url for url in urls}
        for n,f in enumerate(as_completed(futures),1):
            url=futures[f]
            try:details[url]=detail_fields(f.result())
            except Exception as exc:failures[url]=str(exc)
            if n%25==0 or n==len(urls):
                print(json.dumps({'details':n,'total':len(urls),'failures':len(failures)}),flush=True)
    result={'indexes':indexes,'rows':rows,'details':details,'failures':failures}
    (cache/'parsed-manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({'rows':len(rows),'detail_urls':len(urls),'parsed':len(details),'failures':failures},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
