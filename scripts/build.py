#!/usr/bin/env python3
"""Build the SQLite catalog and a portable HTML snapshot (standard library only)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile

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
        if not row['sources'] or not row['locations'] or not row['kami']:
            raise ValueError(f'Missing evidence, location or deity list: {row["id"]}')
        for source in row['sources']:
            if not source['url'].startswith('https://'):
                raise ValueError('Source URL must use HTTPS.')
        for item in row['kami'] + row['locations'] + row['facts']:
            if not item['sources'] or any(type(i) is not int or not 0 <= i < len(row['sources']) for i in item['sources']):
                raise ValueError(f'Invalid field citation: {row["id"]}')
        if any(not 0 <= i < len(row['sources']) for i in row['noteSources']):
            raise ValueError(f'Invalid note citation: {row["id"]}')
        for location in row['locations']:
            if location['id'] in location_ids:
                raise ValueError(f'Duplicate location id: {location["id"]}')
            location_ids.add(location['id'])
            if not (-90 <= location['lat'] <= 90 and -180 <= location['lon'] <= 180):
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


def build_database(rows, prefectures, catalog):
    output = ROOT / 'database' / 'catalog.sqlite'
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
                    db.execute('INSERT INTO shrine_sources VALUES (?,?,?)',(sid,i,source))
                for i,l in enumerate(r['locations']):
                    db.execute('INSERT INTO locations VALUES (?,?,?,?,?,?,?,?,?)',
                               (l['id'],sid,i,l['name'],l['label'],l['address'],l['lat'],l['lon'],l['precision']))
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
        output.write_bytes(temp.read_bytes())
    return output


def build_offline(rows, prefectures):
    html=(ROOT/'index.html').read_text(encoding='utf-8')
    css=(ROOT/'web/atlas.css').read_text(encoding='utf-8')
    js=(ROOT/'web/atlas.js').read_text(encoding='utf-8')
    inline=json.dumps({'shrines':rows,'prefectures':prefectures},ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
    html=html.replace('<link rel="stylesheet" href="web/atlas.css">','<style>\n'+css+'\n</style>')
    html=html.replace('<script src="web/atlas.js" defer></script>',
                      '<script>window.ATLAS_INLINE_DATA='+inline+';</script>\n<script>\n'+js+'\n</script>')
    html=html.replace('资料分离版 v0.2','单文件离线版 v0.2').replace(
        '页面读取独立资料文件；另提供单文件离线版本。','资料与地图均已内嵌；打开外部来源页面时需要联网。')
    output=ROOT/'offline/tottori-shrine-atlas.html'
    output.write_text(html,encoding='utf-8')
    return output


def main():
    catalog=read_json('data/catalog.json')
    rows=[r for collection in catalog['collections'] for r in read_json(collection)]
    prefectures=read_json(catalog['map'])
    validate(rows,prefectures)
    database=build_database(rows,prefectures,catalog)
    offline=build_offline(rows,prefectures)
    print(json.dumps({'shrines':len(rows),'locations':sum(len(r['locations']) for r in rows),
        'prefectures':len(prefectures),'database':str(database.relative_to(ROOT)),
        'offline':str(offline.relative_to(ROOT))},ensure_ascii=False))


if __name__=='__main__':
    main()
