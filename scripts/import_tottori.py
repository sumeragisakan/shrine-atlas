#!/usr/bin/env python3
"""Import the audited Jinjacho directory manifest without inventing missing facts."""
from __future__ import annotations

from collections import Counter,defaultdict
import copy
import json
from pathlib import Path
import re
import runpy
import sys
import unicodedata

ROOT=Path(__file__).resolve().parents[1]
DATE='2026-10-29'
MUNICIPALITIES={
 '鳥取市':('tottori-city','东部'),'米子市':('yonago','西部'),'倉吉市':('kurayoshi','中部'),
 '境港市':('sakaiminato','西部'),'岩美町':('iwami','东部'),'八頭町':('yazu','东部'),
 '若桜町':('wakasa','东部'),'智頭町':('chizu','东部'),'三朝町':('misasa','中部'),
 '琴浦町':('kotoura','中部'),'湯梨浜町':('yurihama','中部'),'北栄町':('hokuei','中部'),
 '日吉津村':('hiezu','西部'),'大山町':('daisen','西部'),'南部町':('nanbu','西部'),
 '伯耆町':('houki','西部'),'江府町':('kofu','西部'),'日野町':('hino','西部'),
 '日南町':('nichinan','西部')}


def key(text):
    text=unicodedata.normalize('NFKC',text)
    # Orthographic equivalence for shrine identity matching only, never for deities.
    text=text.translate(str.maketrans({'稻':'稲','瀧':'滝','竃':'竈','嶋':'島','鬚':'髭','髙':'高','﨑':'崎','冨':'富','碕':'崎'}))
    return re.sub(r'\s+','',re.split(r'[（(〈【<]',text)[0]).strip()


def published(text):
    return bool(text and re.sub(r'[\s\-―ー－—–]+','',text) not in ('','不詳','不明','未詳','未記載','なし','無し'))


def split_names(raw):
    # Do not harmonize kanji, divine identities, or source role annotations.
    tokens=[];part=[];depth=0
    for char in raw:
        if char in '（([［【「《':depth+=1
        if char in '）)]］】」》':depth=max(0,depth-1)
        if depth==0 and char in '、，,;；\n\r\t　':
            text=''.join(part).strip()
            if text:tokens.append(text)
            part=[]
        else:part.append(char)
    if ''.join(part).strip():tokens.append(''.join(part).strip())
    return tokens or [raw.strip()]


def source(label,url,covers,kind='神社庁目录'):
    return {'label':label,'url':url,'kind':kind,'covers':covers,'checked':DATE,'published':None}


def inside(x,y,ring):
    hit=False
    for a,b in zip(ring,ring[1:]):
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:hit=not hit
    return hit


def main():
    cache=Path(sys.argv[1]).resolve()
    manifest=json.loads((cache/'parsed-manifest.json').read_text())
    helper=runpy.run_path(str(ROOT/'scripts/collect_tottori.py'))
    parse=helper['detail_fields'];Page=helper['Page'];Fetcher=helper['Fetcher']
    fetcher=Fetcher(cache)
    catalog=json.loads((ROOT/'data/catalog.json').read_text())
    bird_collections=next((r['collections']for r in catalog.get('regions',[])if r['code']==31),catalog['collections'])
    existing=[r for name in bird_collections for r in json.loads((ROOT/name).read_text())]
    seed_path=Path(sys.argv[3]) if len(sys.argv)>3 else None
    if seed_path:existing=json.loads(seed_path.read_text())
    curated=[r for r in existing if r.get('record_status')=='research_enriched' or not r.get('directory')]
    curated_by_url={s['url']:r for r in curated for s in r['sources'] if 'tottori-jinjacho.jp/pages/' in s['url']}
    curated_by_name={key(r['name']):r for r in curated}
    used_seeds=set()
    # Find alternate, publicly linked detail URLs within each municipality's navigation.
    nav=defaultdict(set)
    for path in cache.glob('page-*.html'):
        page=Page(path.read_text())
        for a in page.root.nodes('a'):
            href=a.attrs.get('href','');name=a.text()
            if re.fullmatch(r'(?:https://tottori-jinjacho.jp)?/pages/\d+/',href) and name:
                nav[key(name)].add('https://tottori-jinjacho.jp'+href if href.startswith('/') else href)
    corrections=[];rows=[];next_no=max((r['no'] for r in curated),default=0)+1
    raw_geo=Path(sys.argv[2]) if len(sys.argv)>2 else None
    polygons=None
    if raw_geo and raw_geo.exists():
        shape=next(f['geometry'] for f in json.loads(raw_geo.read_text())['features'] if f['properties']['id']==31)
        polygons=shape['coordinates'] if shape['type']=='MultiPolygon' else [shape['coordinates']]
    registry_path=ROOT/'data/research/tottori-registry.json'
    registry=json.loads(registry_path.read_text()) if registry_path.exists() else {}
    for entry in manifest['rows']:
        municipality=next((name for name in MUNICIPALITIES if entry['index_label'].startswith(name)),None)
        if not municipality:raise ValueError('Unknown municipality: '+str(entry))
        chosen=entry['url'];detail=manifest['details'].get(chosen)
        valid=bool(detail and key(detail['fields'].get('神社名',''))==key(entry['name']))
        original_status='matched' if valid else ('unlinked' if not chosen else 'profile_unavailable' if detail and not detail['fields'].get('神社名') else 'identity_mismatch')
        if not valid:
            # Candidate URLs must have been observed in public navigation, never guessed.
            for url in sorted(nav.get(key(entry['name']),set())):
                try:
                    candidate=manifest['details'].get(url) or parse(fetcher.fetch(url))
                except Exception:continue
                fields=candidate['fields'];address=re.sub(r'\s+','',unicodedata.normalize('NFKC',fields.get('住所',''))).replace('大字','')
                listed=re.sub(r'\s+','',unicodedata.normalize('NFKC',entry['listed_address'])).replace('大字','')
                if key(fields.get('神社名',''))==key(entry['name']) and (address.startswith(listed) or listed.startswith(address) and address):
                    detail=candidate;chosen=url;valid=True
                    corrections.append({'number':entry['number'],'name':entry['name'],'original_url':entry['url'],'resolved_url':url})
                    break
        if not valid:detail=None
        fields=detail['fields'] if detail else {}
        raw_kami=fields.get('祭神',fields.get('御祭神','')).strip()
        deity_ok=published(raw_kami)
        seed=curated_by_url.get(chosen) if chosen else None
        if not seed:
            candidate=curated_by_name.get(key(entry['name']))
            if candidate and any(key(entry['listed_address']) in key(l['address']) for l in candidate['locations']):seed=candidate
        if seed and seed['id'] in used_seeds:raise ValueError('Curated profile used twice: '+seed['id'])
        if seed:used_seeds.add(seed['id'])
        if seed:
            record=copy.deepcopy(seed);record['record_status']='research_enriched'
            record['municipality']=municipality
            if municipality=='鳥取市':record['aliases']+=['鸟取市']
            if municipality=='倉吉市':record['aliases']+=['仓吉市']
            if municipality=='湯梨浜町':record['aliases']+=['汤梨滨町']
        else:
            record={'id':f'tottori-{entry["number"]:04d}','no':next_no,'prefecture_code':31,
                    'name':entry['name'],'kana':re.sub(r'\s+',' ',fields.get('よみ','')).strip(),
                    'area':MUNICIPALITIES[municipality][1],'municipality':municipality,'aliases':[],
                    'headline':'祭神未公布','tags':['神社庁名录'],'intro':f'位于鸟取县{municipality}，对应神社庁名录第{entry["number"]}号。',
                    'sources':[],'kami':[],'locations':[],'facts':[],'note':'','noteSources':[],
                    'checked':DATE,'media':[],'record_status':'directory_imported'}
            next_no+=1
        def add_source(s):
            for i,old in enumerate(record['sources']):
                if old['url']==s['url']:return i
            record['sources'].append(s);return len(record['sources'])-1
        index_source=add_source(source('鳥取縣神社廳｜'+entry['index_label'],entry['index_url'],'市町村名录中的名称、所在地及条目编号'))
        detail_source=add_source(source('鳥取縣神社廳｜'+entry['name'],chosen,'神社基本资料、祭神原表、旧社格与来源网页地图参考点')) if valid else None
        record['directory']={'number':entry['number'],'index_name':entry['name'],
            'index_url':entry['index_url'],'listed_address':entry['listed_address'],
            'original_detail_url':entry['url'],'detail_url':chosen if valid else None,
            'detail_status':'resolved_link' if valid and original_status!='matched' else original_status,
            'checked':DATE,'source_sha256':detail['html_sha256'] if valid else None}
        record['availability']={'kami':'published' if deity_ok or seed and record['kami'] else 'not_published',
            'history':'source_available' if detail and detail['history'] else 'not_published'}
        record['source_fields']={'kami_verbatim':raw_kami,'former_rank':fields.get('旧社格','').strip()}
        if not seed:
            if deity_ok:
                names=split_names(raw_kami)
                record['kami']=[{'role':'祭神（神社庁原表，未另判主配）','names':names,'sources':[detail_source]}]
                record['headline']='・'.join(names[:2])+(' 等' if len(names)>2 else '')
                if len(record['headline'])>65:record['headline']=record['headline'][:62]+'…'
                if any(re.match(r'^[尊命神][市稲天大]',n) for n in names):record['tags'].append('原表需辨读')
            else:record['tags'].append('祭神未公布')
            address=re.sub(r'\s+','',fields.get('住所','')) or entry['listed_address']
            if not address.startswith('鳥取県'):address='鳥取県'+address
            candidates=detail['points'] if detail else []
            point=next((p for p in candidates if 34.7<p[0]<36 and 132.7<p[1]<135),None)
            status='mapped' if point else 'not_published'
            if point and polygons and not any(inside(point[1],point[0],p[0]) and not any(inside(point[1],point[0],h)for h in p[1:])for p in polygons):
                status='outside_prefecture_needs_review'
            record['locations']=[{'id':record['id']+':1','name':entry['name'],'label':entry['name'],
                'address':address,'lat':point[0] if point else None,'lon':point[1] if point else None,
                'sources':[detail_source if detail_source is not None else index_source],
                'map_status':status,'precision':'神社庁网页地图参考点，非测量坐标或导航入口。' if point else '目录仅提供所在地，未公布可核实的参考坐标；本版未估算位置。'}]
            if status!='mapped':record['tags'].append('未定位' if not point else '坐标待核')
            record['facts'].append({'label':'名录收录','text':f'收录于神社庁“{entry["index_label"]}”目录，编号{entry["number"]}。',
                'sources':[index_source],'nature':'名录事实'})
            rank=record['source_fields']['former_rank']
            if published(rank):record['facts'].append({'label':'旧社格','text':'原目录“旧社格”栏记为：'+rank,'sources':[detail_source],'nature':'来源原栏'})
            history=detail['history'] if detail else ''
            if re.search(r'創[立建始](?:年[代月]|時期|年|時)?(?:は|が|ハ)?(?:不詳|不明|明らかでない|明確でない)',history[:90]):
                record['facts'].append({'label':'创立年代','text':'目录由绪将创立年代记为不详。','sources':[detail_source],'nature':'来源记载'})
            books=[name for name,patterns in [('《延喜式》',('延喜式',)),('《三代实录》',('三代實録','三代実録')),
                    ('《续日本后纪》',('続日本後記','續日本後紀')),('《出云国风土记》',('出雲國風土記','出雲国風土記')),
                    ('《因幡志》',('因幡志','因幡誌')),('《伯耆志》',('伯耆志','伯耆誌'))]if any(p in history for p in patterns)]
            if books:record['facts'].append({'label':'文献检索线索','text':'该页由绪提及'+'、'.join(books)+'；这表示来源页面存在相关叙述，本版未逐条核验古籍原卷及比定。',
                'sources':[detail_source],'nature':'来源中的文献线索'})
            events=[]
            for event in ['例祭','春祭','秋祭','夏祭']:
                m=re.search(event+r'\s*([0-9０-９一二三四五六七八九十]+月[0-9０-９一二三四五六七八九十]+日)',fields.get('祭祀',''))
                if m:events.append(event+' '+m[1])
            if events:record['facts'].append({'label':'祭典日期线索','text':'目录列示：'+'；'.join(events)+'。具体举行方式及当年安排请向神社核实。',
                'sources':[detail_source],'nature':'来源列示日期'})
            if history:record['note']='本条依据神社庁公开资料录入。源页面另有由绪；创立、合祀、迁座与文献比定尚未逐社作独立历史考证。'
            else:record['note']='当前来源仅能支持已显示的名录字段，尚未取得可核实的完整由绪；未依据社名推测祭神或创立年代。'
            record['noteSources']=[detail_source if valid else index_source]
        if original_status=='identity_mismatch' and not valid:
            record['tags'].append('链接待核')
            record['note']+=' 原目录详情链接指向名称不同的页面，本版未将该页的祭神或坐标分配给本条。'
        elif original_status=='profile_unavailable' and not valid:
            record['tags'].append('详情暂缺')
            record['note']+=' 原目录有详情链接，但页面未提供可辨识的神社资料，暂仅采用地域名录。'
        elif record['directory']['detail_status']=='resolved_link':
            record['note']+=' 原地域目录的链接有误；本版依网站导航中可验证的同名、同所在地详情页修正链接。'
        for l in record['locations']:l.setdefault('map_status','mapped' if l['lat'] is not None else 'not_published')
        reg=registry.get(str(entry['number']))
        if reg:
            ref=add_source(reg['source']);record['entity_registry']=reg['evidence']
            if reg['evidence']['state']=='closed_by_merger':
                record['tags'].append('法人登记已关闭')
                record['facts'].append({'label':'法人登记资料','text':f'政府法人资料显示，编号{reg["evidence"]["corporate_number"]}的登记记录于{reg["evidence"]["closed_date"]}因“合併による解散等”关闭。登记所在地：{reg["evidence"].get("registered_address", "未记载")}（此为法人登记地址，未作现场定位）。登记关闭不等于社殿已拆除或祭祀已经停止。',
                    'sources':[ref],'nature':'法人登记状态'})
        record['aliases']=list(dict.fromkeys(record['aliases']))
        record['tags']=list(dict.fromkeys(record['tags']))
        rows.append(record)
    if len(used_seeds)!=len(curated):raise ValueError('Some enriched profiles were not matched')
    if len({r['id']for r in rows})!=len(rows):raise ValueError('Duplicate stable ids')
    if len(rows)!=len(manifest['rows']) or len({r['directory']['number']for r in rows})!=len(rows):raise ValueError('Directory reconciliation failed')
    out=ROOT/'data/shrines/tottori';out.mkdir(parents=True,exist_ok=True)
    collections=[]
    for municipality,(slug,area)in MUNICIPALITIES.items():
        group=sorted((r for r in rows if r['municipality']==municipality),key=lambda r:r['no'])
        path=out/(slug+'.json');path.write_text(json.dumps(group,ensure_ascii=False,indent=2)+'\n');collections.append(str(path.relative_to(ROOT)))
    counts=[]
    for municipality in MUNICIPALITIES:
        group=[r for r in rows if r['municipality']==municipality]
        counts.append({'municipality':municipality,'area':MUNICIPALITIES[municipality][1],'records':len(group),
            'with_deities':sum(bool(r['kami'])for r in group),'mapped_locations':sum(l['map_status']=='mapped'for r in group for l in r['locations']),
            'without_coordinates':sum(not any(l['map_status']=='mapped'for l in r['locations'])for r in group)})
    coverage={'checked':DATE,'scope':'鳥取縣神社廳・22个地域目录的全部824条记录',
        'scope_note':'覆盖该公开名录，不等同于证明县内每一处小祠、境内末社、未列名设施均已收录；不把法人登记关闭等同于社殿消失或祭祀停止。',
        'directory_rows':len(manifest['rows']),'records':len(rows),'directory_indexes':len(manifest['indexes']),
        'municipalities':counts,'details_matched':sum(r['directory']['detail_url']is not None for r in rows),
        'with_deities':sum(bool(r['kami'])for r in rows),'mapped_locations':sum(l['map_status']=='mapped'for r in rows for l in r['locations']),
        'enriched_records':sum(r['record_status']=='research_enriched'for r in rows),'link_corrections':corrections,
        'missing_fields':[{'id':r['id'],'number':r['directory']['number'],'name':r['name'],'municipality':r['municipality'],
            'deities_missing':not bool(r['kami']),'coordinates_missing':not any(l['map_status']=='mapped'for l in r['locations']),
            'detail_status':r['directory']['detail_status']}for r in rows if not r['kami']or not any(l['map_status']=='mapped'for l in r['locations'])or r['directory']['detail_url']is None],
        'indexes':manifest['indexes']}
    (ROOT/'data/coverage-tottori.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2)+'\n')
    if catalog.get('regions'):
        region=next(r for r in catalog['regions']if r['code']==31);region['collections']=collections
        collections=[c for r in catalog['regions']for c in r['collections']]
    catalog.update({'schema_version':3 if catalog.get('regions')else 2,'checked':DATE,'collections':collections,'coverage':'data/coverage-tottori.json',
                    'coverage_note':coverage['scope']+'；原资料缺失或有差异的字段另行标注。'})
    (ROOT/'data/catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n')
    old=ROOT/'data/shrines/tottori.json'
    if old.exists():old.unlink()
    print(json.dumps({k:v for k,v in coverage.items()if k not in ['municipalities','missing_fields','indexes','link_corrections']},ensure_ascii=False))
    print('link corrections',json.dumps(corrections,ensure_ascii=False))


if __name__=='__main__':main()
