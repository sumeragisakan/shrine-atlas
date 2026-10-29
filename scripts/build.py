#!/usr/bin/env python3
"""Build the SQLite catalog and a portable HTML snapshot (standard library only)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import argparse
import gzip
import base64
from import_prefecture import SLUGS

ROOT = Path(__file__).resolve().parents[1]


def read_json(path: str):
    resolved = (ROOT / path).resolve()
    if not resolved.is_relative_to(ROOT):
        raise ValueError(f'Path outside repository: {path}')
    return json.loads(resolved.read_text(encoding='utf-8'))


def source_id(url: str) -> str:
    return 'src-' + hashlib.sha256(url.encode()).hexdigest()[:16]


def validate(rows, prefectures):
    known = {p['id'] for p in prefectures}
    if known != set(range(1, 48)):
        raise ValueError('The map must contain all 47 unique prefecture codes.')
    ids, location_ids = set(), set()
    for row in rows:
        if row['id'] in ids:
            raise ValueError(f'Duplicate shrine id: {row["id"]}')
        ids.add(row['id'])
        if row['prefecture_code'] not in known:
            raise ValueError(f'Unknown prefecture: {row["id"]}')
        if not row['sources'] or not row['locations']:
            raise ValueError(f'Missing evidence or location record: {row["id"]}')
        if not row['kami'] and row.get('availability',{}).get('kami') != 'not_published':
            raise ValueError(f'Unexplained empty deity list: {row["id"]}')
        for source in row['sources']:
            if not source['url'].startswith(('https://','http://')):
                raise ValueError('Source URL must be a public HTTP(S) page.')
        for item in row['kami'] + row['locations'] + row['facts']:
            if not item['sources'] or any(type(i) is not int or not 0 <= i < len(row['sources']) for i in item['sources']):
                raise ValueError(f'Invalid field citation: {row["id"]}')
        if any(not 0 <= i < len(row['sources']) for i in row['noteSources']):
            raise ValueError(f'Invalid note citation: {row["id"]}')
        for location in row['locations']:
            if location['id'] in location_ids:
                raise ValueError(f'Duplicate location id: {location["id"]}')
            location_ids.add(location['id'])
            lat,lon=location['lat'],location['lon']
            if (lat is None) != (lon is None) or (lat is None and location['map_status'] != 'not_published'):
                raise ValueError(f'Unexplained missing reference point: {location["id"]}')
            if lat is not None and not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError(f'Invalid reference point: {location["id"]}')
        for media in row.get('media', []):
            for key in ('id', 'kind', 'path', 'caption', 'source_url', 'creator', 'license', 'checked_at'):
                if not media.get(key):
                    raise ValueError(f'Missing media metadata: {row["id"]}/{key}')
            if media['kind'] not in ('image', 'model'):
                raise ValueError(f'Invalid media kind: {media["kind"]}')
            if media.get('location_id') and media['location_id'] not in {l['id'] for l in row['locations']}:
                raise ValueError('Media location must belong to the same shrine.')
            asset = (ROOT / media['path']).resolve()
            if not asset.is_relative_to(ROOT / 'media') or not asset.is_file():
                raise ValueError(f'Media path must be an existing file under media/: {media["path"]}')
            checksum = hashlib.sha256(asset.read_bytes()).hexdigest()
            if media.get('sha256') and media['sha256'] != checksum:
                raise ValueError(f'Media checksum mismatch: {media["id"]}')


def build_database(rows, prefectures, catalog, output_path='database/catalog.sqlite'):
    output = ROOT / output_path
    output.parent.mkdir(parents=True,exist_ok=True)
    # Build a fresh DB, then replace the derived artifact only after all checks pass.
    with tempfile.TemporaryDirectory(prefix='atlas-db-') as folder:
        temp = Path(folder) / 'catalog.sqlite'
        db = sqlite3.connect(temp)
        try:
            db.executescript((ROOT / 'database/schema.sql').read_text(encoding='utf-8'))
            db.executemany('INSERT INTO metadata VALUES (?,?)', [
                ('schema_version', str(catalog['schema_version'])),
                ('checked_at', catalog['checked']),
                ('source_of_truth', 'data/catalog.json and listed collection JSON files'),
                ('coverage_note', catalog['coverage_note'])])
            db.executemany('INSERT INTO prefectures VALUES (?,?)', [(p['id'],p['name']) for p in prefectures])
            known_sources = {}
            for r in rows:
                sid = r['id']
                db.execute('INSERT INTO shrines VALUES (?,?,?,?,?,?,?,?,?,?,?)', (
                    sid,r['prefecture_code'],r['no'],r['name'],r['kana'],r['area'],r['municipality'],
                    r['headline'],r['intro'],r['note'],r['checked']))
                for table, key, field in [('aliases','aliases','alias'), ('tags','tags','tag')]:
                    db.executemany(f'INSERT INTO {table} (shrine_id,ordinal,{field}) VALUES (?,?,?)',
                                   [(sid,i,text) for i,text in enumerate(r[key])])
                refs=[]
                for i,s in enumerate(r['sources']):
                    source=source_id(s['url']); refs.append(source)
                    if source in known_sources and known_sources[source] != s['url']:
                        raise ValueError('Source identifier hash collision.')
                    if source not in known_sources:
                        db.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?)',
                                   (source,s['url'],s['label'],s['kind'],s['covers'],s['checked'],s.get('published')))
                        known_sources[source]=s['url']
                        extra={k:v for k,v in s.items()if k not in ['url','label','kind','covers','checked','published']}
                        if extra:db.execute('INSERT INTO source_retrievals VALUES (?,?)',(source,json.dumps(extra,ensure_ascii=False)))
                    db.execute('INSERT INTO shrine_sources VALUES (?,?,?)',(sid,i,source))
                for i,l in enumerate(r['locations']):
                    db.execute('INSERT INTO locations VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                               (l['id'],sid,i,l['name'],l['label'],l['address'],l['lat'],l['lon'],l['precision'],l['map_status'],l.get('address_status','published'),l.get('legacy_address')))
                    db.executemany('INSERT INTO location_sources VALUES (?,?,?)',
                                   [(l['id'],refs[ref],n) for n,ref in enumerate(l['sources'])])
                for i,g in enumerate(r['kami']):
                    group=f'{sid}:group:{i}'
                    db.execute('INSERT INTO deity_groups VALUES (?,?,?,?)',(group,sid,i,g['role']))
                    db.executemany('INSERT INTO deity_mentions VALUES (?,?,?)',[(group,n,name) for n,name in enumerate(g['names'])])
                    db.executemany('INSERT INTO deity_group_sources VALUES (?,?,?)',[(group,refs[ref],n) for n,ref in enumerate(g['sources'])])
                for i,f in enumerate(r['facts']):
                    note=f'{sid}:fact:{i}'
                    db.execute('INSERT INTO historical_notes VALUES (?,?,?,?,?,?)',(note,sid,i,f['label'],f['text'],f['nature']))
                    db.executemany('INSERT INTO historical_note_sources VALUES (?,?,?)',[(note,refs[ref],n) for n,ref in enumerate(f['sources'])])
                db.executemany('INSERT INTO research_note_sources VALUES (?,?,?)',[(sid,refs[ref],n) for n,ref in enumerate(r['noteSources'])])
                if r.get('directory'):
                    d=r['directory']
                    db.execute('INSERT INTO directory_entries VALUES (?,?,?,?,?,?,?,?,?,?)',(
                        sid,d['number'],d['index_name'],d['index_url'],d['listed_address'],d['original_detail_url'],
                        d['detail_url'],d['detail_status'],d['source_sha256'],d['checked']))
                q=r.get('availability',{});f=r.get('source_fields',{})
                db.execute('INSERT INTO record_quality VALUES (?,?,?,?,?,?)',(
                    sid,r.get('record_status','research_enriched'),q.get('kami','published'),q.get('history','source_available'),
                    f.get('kami_verbatim',''),f.get('former_rank','')))
                if r.get('provenance'):db.execute('INSERT INTO record_provenance VALUES (?,?)',(sid,json.dumps(r['provenance'],ensure_ascii=False)))
                if r.get('entity_registry'):
                    e=r['entity_registry'];s=next(s for s in r['sources'] if 'info.gbiz.go.jp' in s['url'])
                    db.execute('INSERT INTO entity_registry VALUES (?,?,?,?,?,?)',(
                        sid,e['corporate_number'],e['state'],e.get('closed_date'),e.get('registered_address'),source_id(s['url'])))
                for m in r.get('media',[]):
                    checksum=hashlib.sha256((ROOT/m['path']).read_bytes()).hexdigest()
                    db.execute('INSERT INTO media_assets VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(
                        m['id'],sid,m.get('location_id'),m['kind'],m['path'],m['caption'],m['source_url'],
                        m['creator'],m['license'],m.get('license_url'),checksum,m['checked_at']))
            db.commit()
            problems=db.execute('PRAGMA foreign_key_check').fetchall()
            if problems or db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError(f'SQLite integrity check failed: {problems}')
            if db.execute('SELECT COUNT(*) FROM shrines').fetchone()[0] != len(rows):
                raise ValueError('Shrine import count mismatch.')
            # Ensure textual deity lists and citation order survived the relational import.
            for r in rows:
                groups=db.execute('SELECT id,role_text FROM deity_groups WHERE shrine_id=? ORDER BY ordinal',(r['id'],)).fetchall()
                for (gid,role),original in zip(groups,r['kami'],strict=True):
                    names=[v[0] for v in db.execute('SELECT name_verbatim FROM deity_mentions WHERE group_id=? ORDER BY ordinal',(gid,))]
                    if names != original['names'] or role != original['role']:
                        raise ValueError('A deity list changed during database import.')
            db.execute('VACUUM')
        finally:
            db.close()
        raw=temp.read_bytes()
        output.write_bytes(gzip.compress(raw,compresslevel=9,mtime=0)if output_path.endswith('.gz')else raw)
    return output


def region_specs():
    prefectures=read_json('data/maps/prefectures.json')
    old=read_json('data/catalog.json')
    bird_collections=[c for c in old.get('collections',[])if c.startswith('data/shrines/tottori/')]
    if not bird_collections:bird_collections=[str(p.relative_to(ROOT))for p in sorted((ROOT/'data/shrines/tottori').glob('*.json'))]
    regions=[]
    for pref in prefectures:
        code=pref['id'];slug=SLUGS[code-1]
        coverage_path='data/coverage-tottori.json'if code==31 else f'data/coverage/{code:02d}-{slug}.json'
        region={'code':code,'name':pref['name'],'slug':slug,'status':'pending','records':0,'mapped_locations':0,'with_deities':0,'collections':[],
            'coverage':None,'database':None,'offline':None,'historical_only_records':0,'agency_rows':0}
        if (ROOT/coverage_path).exists():
            cov=read_json(coverage_path);collections=bird_collections if code==31 else cov['collections']
            region.update({'status':'ready','records':cov['records'],'mapped_locations':cov['mapped_locations'],'with_deities':cov['with_deities'],
                'collections':collections,'coverage':coverage_path,'checked':cov['checked'],'scope_note':cov['scope_note'],
                'historical_only_records':cov.get('historical_only_records',0),'agency_rows':cov.get('agency_rows',cov['records']),
                'database':'database/catalog.sqlite'if code==31 else f'database/prefectures/{code:02d}-{slug}.sqlite.gz',
                'offline':'offline/tottori-shrine-atlas.html'if code==31 else f'offline/prefectures/{code:02d}-{slug}.html'})
        regions.append(region)
    catalog={'schema_version':3,'version':'0.5','checked':'2026-10-30','map':'data/maps/prefectures.json','default_prefecture':0,
        'regions':regions,'collections':[c for r in regions for c in r['collections']],
        'coverage_note':'机构公开名录与明确标记的研究会历史条目；不同来源的范围和缺失字段逐地区说明。',
        'totals':{'regions':sum(r['status']=='ready'for r in regions),'records':sum(r['records']for r in regions),
            'mapped_locations':sum(r['mapped_locations']for r in regions),'with_deities':sum(r['with_deities']for r in regions),
            'historical_only_records':sum(r['historical_only_records']for r in regions)}}
    return prefectures,catalog


def build_offline(rows,prefectures,coverage,catalog,code,output_path):
    html=(ROOT/'index.html').read_text();css=(ROOT/'web/atlas.css').read_text();js=(ROOT/'web/atlas.js').read_text();core=(ROOT/'web/explore-core.js').read_text()
    # Regional standalone files link through the latest offline nationwide index.
    # They do not need regeneration whenever another prefecture is committed.
    local_catalog=json.loads(json.dumps(catalog))
    if code:
        for r in local_catalog['regions']:
            if r['code']!=code:
                for k in ['records','mapped_locations','with_deities','historical_only_records','agency_rows']:r.pop(k,None)
                r['status']='via_national_index';r['collections']=[]
    prefix='../../'if output_path.startswith('offline/prefectures/')else'../'
    inline=json.dumps({'shrines':rows,'prefectures':prefectures,'coverage':coverage,'catalog':local_catalog,
        'runtime':{'active_prefecture':code,'root_prefix':prefix}},ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
    html=html.replace('<link rel="stylesheet" href="web/atlas.css">','<style>\n'+css+'\n</style>')
    html=html.replace('<script src="web/explore-core.js" defer></script>','<script>\n'+core+'\n</script>')
    packed=base64.b64encode(gzip.compress(inline.encode(),compresslevel=9,mtime=0)).decode()
    html=html.replace('<script src="web/atlas.js" defer></script>','<script>window.ATLAS_PACKED_DATA='+json.dumps(packed)+';</script>\n<script>\n'+js+'\n</script>')
    html=html.replace('资料分离版 v0.5','单文件离线版 v0.5').replace('页面读取独立资料文件；另提供单文件离线版本。','本地区资料已内嵌；切换地区请保留下载包中的其他离线文件。')
    output=ROOT/output_path;output.parent.mkdir(parents=True,exist_ok=True);output.write_text(html)
    return output


def validate_coverage(rows,coverage):
    if len(rows)!=coverage['records']or len({r['id']for r in rows})!=len(rows):raise ValueError('Region reconciliation failed')
    if len({r['no']for r in rows})!=len(rows):raise ValueError('Duplicate display order within region')
    actual={'with_deities':sum(bool(r['kami'])for r in rows),'mapped_locations':sum(l['map_status']=='mapped'for r in rows for l in r['locations'])}
    if any(coverage[k]!=v for k,v in actual.items()):raise ValueError('Coverage totals disagree')
    for m in coverage['municipalities']:
        group=[r for r in rows if r['municipality']==m['municipality']]
        if len(group)!=m['records']:raise ValueError('Municipality total disagrees')


def build_reports(catalog):
    lines=['# 全国整理进度','','来源记录可能含历史未对应／疑似重复条目，不等于独立实存神社数。完成状态表示本批所列来源已经导入、验证，不等于已完成每社现况或由绪考证。','',
        '|代码|都道府县|状态|来源记录|机构记录|历史待核|可标示点位|','|---|---|---|---:|---:|---:|---:|']
    reports=ROOT/'docs/prefectures';reports.mkdir(exist_ok=True)
    for r in catalog['regions']:
        ready=r['status']=='ready';lines.append(f"|{r['code']:02d}|{r['name']}|{'已导入验证'if ready else'待整理'}|{r['records']if ready else'—'}|{r['agency_rows']if ready else'—'}|{r['historical_only_records']if ready else'—'}|{r['mapped_locations']if ready else'—'}|")
        if not ready:continue
        c=read_json(r['coverage']);body=[f"# {r['name']} · 来源范围",'',f"查阅：{c['checked']}。来源记录 {r['records']} 条，机构记录 {r['agency_rows']} 条，未可靠对应的历史条目 {r['historical_only_records']} 条。",'',c['scope_note'],'',f"有祭神资料 {r['with_deities']} 条；可标示参考点 {r['mapped_locations']} 处。",'']
        for agency in c.get('agency_scopes',[]):
            body += ['## '+agency['provider'],'',agency.get('scope_note')or'以实际公开索引为准。','',f"已遍历公开索引：{agency.get('pagination_complete')}；来源异常项：{len(agency.get('failures')or[])}。",'']
            detail=agency.get('profile_counts')or agency.get('detail_completion')
            if detail:body += ['详情读取状态：`'+json.dumps(detail,ensure_ascii=False,separators=(',',':'))+'`。','']
            if agency.get('source_vintage'):body += ['来源版本：'+str(agency['source_vintage'])+'。','']
        body += ['## 核对入口','',f"- [覆盖与异常完整报告](../../{r['coverage']})",f"- [离线页面](../../{r['offline']})",f"- [数据库](../../{r['database']})",'',f"坐标隔离 {len(c.get('coordinate_quarantine',[]))} 项；同名待核分组 {len(c.get('duplicate_candidates',[]))} 组；明确排除来源行 {len(c.get('excluded_source_rows',[]))} 项。",'', '这些数量是来源处理状态，不是全境实存神社统计。历史版本、来源字段错位、公开目录范围不足及未访问详情均按原资料状态保留。','']
        (reports/f"{r['code']:02d}-{r['slug']}.md").write_text('\n'.join(body))
    (ROOT/'docs/NATIONAL_PROGRESS.md').write_text('\n'.join(lines)+'\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prefecture',type=int);parser.add_argument('--registry-only',action='store_true');parser.add_argument('--all',action='store_true');args=parser.parse_args()
    prefectures,catalog=region_specs()
    build_reports(catalog)
    (ROOT/'data/catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n')
    selected=[r for r in catalog['regions']if r['status']=='ready'and (args.prefecture is None or r['code']==args.prefecture)]
    if args.prefecture is not None and not selected:raise ValueError('Prefecture not imported')
    if not args.registry_only:
        for region in selected:
            rows=[r for path in region['collections']for r in read_json(path)];coverage=read_json(region['coverage'])
            validate(rows,prefectures);validate_coverage(rows,coverage)
            db=build_database(rows,prefectures,{**catalog,'coverage_note':coverage['scope_note']},region['database'])
            offline=build_offline(rows,prefectures,coverage,catalog,region['code'],region['offline'])
            print(json.dumps({'code':region['code'],'records':len(rows),'database':str(db.relative_to(ROOT)),'offline':str(offline.relative_to(ROOT))},ensure_ascii=False),flush=True)
    coverage={'scope':'日本全国・地区索引','scope_note':catalog['coverage_note'],'checked':catalog['checked'],'municipalities':[],
        'records':catalog['totals']['records'],'with_deities':catalog['totals']['with_deities'],'mapped_locations':catalog['totals']['mapped_locations'],
        'enriched_records':12,'directory_indexes':0,'indexes':[],'link_corrections':[]}
    build_offline([],prefectures,coverage,catalog,0,'offline/japan-shrine-atlas.html')
    print(json.dumps({'totals':catalog['totals']},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
