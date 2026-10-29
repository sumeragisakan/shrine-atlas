#!/usr/bin/env python3
"""Reconcile one prefecture's cited public agency facts and historical baseline.

Only unique exact name+address matches are joined. Other historical entries
remain explicitly historical, not silently merged or presented as current.
"""
from pathlib import Path
from collections import defaultdict,Counter
import hashlib,json,re,sys,unicodedata

ROOT=Path(__file__).resolve().parents[1]
DATE='2026-10-30'
SLUGS='hokkaido aomori iwate miyagi akita yamagata fukushima ibaraki tochigi gunma saitama chiba tokyo kanagawa niigata toyama ishikawa fukui yamanashi nagano gifu shizuoka aichi mie shiga kyoto osaka hyogo nara wakayama tottori shimane okayama hiroshima yamaguchi tokushima kagawa ehime kochi fukuoka saga nagasaki kumamoto oita miyazaki kagoshima okinawa'.split()

def norm(s):return re.sub(r'\s+','',unicodedata.normalize('NFKC',s or ''))
def name_key(s):
    return re.split(r'[（(＜<]',norm(s))[0].translate(str.maketrans({'稻':'稲','瀧':'滝','竃':'竈','嶋':'島','髙':'高','冨':'富','﨑':'崎'}))
def address_key(s,pref):
    s=norm(s).removeprefix(pref).replace('大字','')
    s=re.sub(r'[‐‑‒–—―−ーｰ]','-',s).replace('丁目','-').replace('番地の','-').replace('番地','-').replace('番','-').replace('号','')
    return s.strip('-')
def municipality(address,pref,listed=None):
    s=norm(address).removeprefix(pref)
    for pattern in [r'^(.+?郡.+?[町村])',r'^(.+?市[^郡市町村]*?区)',r'^(.+?市)',r'^(.+?区)',r'^(.+?[町村])']:
        m=re.match(pattern,s)
        if m:return m[1]
    return listed or '所在地未详'
def published(s):return bool(s and not re.fullmatch(r'[\sー―－—–-]+',s)and norm(s)not in['不明','不詳','不祥','未詳','なし'])
def office(name):return bool(re.fullmatch(r'(?:北海道|.{2,3}[都府県])?神社庁|神社本庁',norm(name)))
def split_names(s):
    out=[];part=[];depth=0
    for c in s:
        if c in '（([［【「':depth+=1
        if c in '）)]］】」':depth=max(0,depth-1)
        if depth==0 and c in '、，,;；\n\r\t　':
            v=''.join(part).strip()
            if v:out.append(v)
            part=[]
        else:part.append(c)
    if ''.join(part).strip():out.append(''.join(part).strip())
    return out
def kami_groups(raw,ref,historical=False):
    if not published(raw):return []
    # Explicit source role markers stay separate; no role is invented.
    marker=list(re.finditer(r'《([^》]+)》',raw));groups=[]
    suffix=' · 历史检索表，非现况确认'if historical else ''
    if marker:
        if raw[:marker[0].start()].strip('、, \n'):
            groups.append({'role':'原表未标主配'+suffix,'names':split_names(raw[:marker[0].start()].strip('、, \n')),'sources':[ref]})
        for i,m in enumerate(marker):
            text=raw[m.end():marker[i+1].start()if i+1<len(marker)else len(raw)].strip('、, \n')
            if text:groups.append({'role':'原表《'+m[1]+'》'+suffix,'names':split_names(text),'sources':[ref]})
    else:groups=[{'role':'祭神（来源原栏，未另判主配）'+suffix,'names':split_names(raw),'sources':[ref]}]
    return [g for g in groups if g['names']]
def inside(x,y,ring):
    hit=False
    for a,b in zip(ring,ring[1:]):
        if(a[1]>y)!=(b[1]>y)and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:hit=not hit
    return hit
def in_pref(lat,lon,geometry):
    polys=geometry['coordinates']if geometry['type']=='MultiPolygon'else[geometry['coordinates']]
    return any(inside(lon,lat,p[0])and not any(inside(lon,lat,h)for h in p[1:])for p in polys)

def import_prefecture(code,baseline_path,agency_paths,geo_path):
    if code==31:raise ValueError('Keep the existing Tottori research dataset unchanged')
    prefectures=json.loads((ROOT/'data/maps/prefectures.json').read_text());pref=next(p['name']for p in prefectures if p['id']==code);slug=SLUGS[code-1]
    baseline=json.loads(Path(baseline_path).read_text());assert int(baseline['code'])==code
    agencies=[]
    for path in agency_paths:
        obj=json.loads(Path(path).read_text())
        if int(obj['code'])!=code:raise ValueError('Wrong agency prefecture')
        agencies.append(obj)
    geometry=next(f['geometry']for f in json.loads(Path(geo_path).read_text())['features']if f['properties']['id']==code)
    agency_rows=[];seen=set();excluded=[]
    for agency in agencies:
        for a in agency.get('records',[]):
            if not a.get('name')or not a['name'].strip()or office(a['name'])or a.get('is_shrine')is False:
                excluded.append({'provider':agency['provider'],'source_id':a.get('source_id'),'reason':'机构办公室或明确非神社条目'if office(a.get('name'))or a.get('is_shrine')is False else'来源未公布可辨识社名，不虚构名称导入'})
                continue
            token=(agency['provider'],str(a['source_id']))
            if token in seen:raise ValueError('Duplicate agency record identifier: '+str(token))
            seen.add(token);agency_rows.append((agency,a))
    old=baseline['records'];old_keys=defaultdict(list);new_keys=defaultdict(list)
    for i,r in enumerate(old):
        for address in [r.get('address'),r.get('address_legacy')]:
            if address:old_keys[(name_key(r['name']),address_key(address,pref))].append(i)
    for i,(agency,r)in enumerate(agency_rows):
        if r.get('address')and r.get('address_precision')!='town':new_keys[(name_key(r['name']),address_key(r['address'],pref))].append(i)
    pairs={};used_old=set()
    for key,ids in new_keys.items():
        candidates=set(old_keys.get(key,[]))
        if len(ids)==1 and len(candidates)==1:
            j=next(iter(candidates))
            if j not in used_old:pairs[ids[0]]=j;used_old.add(j)
    rows=[];quarantine=[];dedup_candidates=[]
    def make(a,agency,historical,legacy=None):
        vintage=(agency or {}).get('source_vintage');legacy_agency=bool((agency or {}).get('historical_source'))
        source_identity=str(a['source_id']);identity=('national:'+source_identity)if historical else agency['provider']+':'+source_identity
        uid=f'{code:02d}-'+('history-'if historical else 'agency-')+hashlib.sha256(identity.encode()).hexdigest()[:14]
        sources=[]
        def add(label,url,kind,covers,**extra):
            if not url:raise ValueError('Missing factual source URL')
            for i,s in enumerate(sources):
                if s['url']==url:return i
            sources.append({'label':label,'url':url,'kind':kind,'covers':covers,'checked':DATE,'published':None,**extra});return len(sources)-1
        tags=[];facts=[];groups=[];old_address=a.get('address_legacy')if historical else None
        if historical:
            ref=add('神社史研究会｜'+pref+'・条目'+source_identity,a['profile_url'],'研究会检索资料（含历史调查）',
                '神社名、当前／平成5年当时地址栏及祭神原表，读取自该地区完整检索结果；详情入口由公开结果提供，未逐页确认现况。',
                retrieved_from=baseline['query_url'],request=baseline['request'],profile_fetched=False)
            address=a.get('address')or old_address or ''
            addr_ref=ref;deity_ref=ref;coord_ref=ref
            tags+=['研究会名录','历史资料待核']
            if not a.get('address')and old_address:tags.append('历史地址')
            note='研究会检索资料包括平成5年（1993）调查及合并前地址。本条未与当地机构名录作可靠同址匹配，不能当作现今神社状态、现址或当前祭神确认。'
            raw=a.get('kami_verbatim')or '';groups=kami_groups(raw,ref,True)
            facts.append({'label':'来源版本','text':'研究会结果页同时列示当前地址栏与平成5年当时地址栏；本项目保留来源原栏，不自动把旧地址更新为现址。','nature':'来源范围','sources':[ref]})
        else:
            urls=a.get('field_source_urls')or {};default=a.get('profile_url')or a.get('index_url')
            def field_ref(field):return add(agency['provider']+'｜'+a['name'],urls.get(field)or default,'神社机构公开资料'+('（目录版本'+str(vintage)+'）'if vintage else''),'对应公开字段；不推断来源未公布的祭神、现况或坐标。')
            ref=field_ref('name');address=a.get('address')or '';addr_ref=field_ref('address')if address else ref
            raw=a.get('kami_verbatim')or '';deity_ref=field_ref('kami_verbatim')if raw else ref;groups=kami_groups(raw,deity_ref,legacy_agency)
            coord_ref=add(agency['provider']+'｜地图参考点',a.get('coordinate_source_url')or urls.get('lat')or default,'机构网页地图参考点','该公开页面或地图数据实际提供的经纬度；非地址估算或导航入口。')if a.get('lat')is not None else ref
            tags=['机构公开名录'];note='本条依据机构公开名录字段整理。收录范围以该机构实际公开目录为限，未独立逐社核验全部由绪或祭祀现况。'
            if vintage:tags.append('目录版本'+str(vintage));note+=' 原目录标示版本为'+str(vintage)+'，个别字段可能另有更新，不能当作现况确认。'
            if a.get('address_precision')=='town':tags.append('仅列町域');note+=' 来源所在地仅到町域，不能当作番地或现场入口。'
            if a.get('source_field_anomalies'):tags.append('来源字段待核');note+=' 来源字段存在错位或异常，未据此推定缺失值。'
            rank=a.get('rank')or ''
            if published(rank):facts.append({'label':'旧社格','text':'来源原栏：'+rank,'nature':'来源原栏','sources':[field_ref('rank')]})
            if legacy:
                oldref=add('神社史研究会｜历史对应条目'+legacy['source_id'],legacy['profile_url'],'研究会历史对应资料',
                    '按唯一的社名及规范化地址对应；保留旧表祭神及地址，不能自动解释为当前奉祀。',retrieved_from=baseline['query_url'],request=baseline['request'],profile_fetched=False)
                oldraw=legacy.get('kami_verbatim')or ''
                if oldraw and oldraw!=raw:groups+=kami_groups(oldraw,oldref,True);tags.append('含历史祭神表')
                old_address=legacy.get('address_legacy')or None
                facts.append({'label':'历史检索表对应','text':'同一地区结果中社名与地址可唯一对应；历史表与机构字段分别保留，不把来源间的差异直接订正为统一结论。','nature':'资料对应','sources':[oldref,ref]})
        if not address:address=old_address or '所在地未公布'
        if address!='所在地未公布'and not re.match(r'^(北海道|東京都|京都府|大阪府|.{2,3}県)',address):address=pref+address
        lat=a.get('lat');lon=a.get('lon');status='not_published'
        if lat is not None or lon is not None:
            if lat is None or lon is None:raise ValueError('Unpaired coordinate')
            lat,lon=float(lat),float(lon);status='mapped'if in_pref(lat,lon,geometry)else'outside_prefecture_needs_review'
            if a.get('coordinate_kind')=='published_map_viewport':status='source_map_viewport'
            if status!='mapped':tags.append('坐标待核');quarantine.append({'id':uid,'name':a['name'],'lat':lat,'lon':lon,'source':sources[coord_ref]['url'],'reason':status})
        if status=='not_published':tags.append('未定位')
        if not groups:tags.append('祭神未公布')
        municipality_name=municipality(address,pref,a.get('listed_region'))
        headline='・'.join(groups[0]['names'][:2])+(' 等'if len(groups[0]['names'])>2 else '')if groups else'祭神未公布'
        if historical or legacy_agency or (groups and not published(a.get('kami_verbatim'))):headline='历史表 · '+headline
        if len(headline)>80:headline=headline[:77]+'…'
        row={'id':uid,'no':len(rows)+1,'prefecture_code':code,'name':a['name'],'kana':a.get('kana')or'','area':a.get('branch')or'全域','municipality':municipality_name,
            'aliases':[],'headline':headline,'tags':tags,'intro':f'{pref}{municipality_name}的来源记录；具体所在地与祭神保留逐项出处。',
            'sources':sources,'kami':groups,'locations':[{'id':uid+':1','name':a['name'],'label':a['name'],'address':address,
                'lat':lat,'lon':lon,'sources':list(dict.fromkeys([addr_ref,coord_ref]))if lat is not None else[addr_ref],
                'map_status':status,'precision':'来源地图视窗中心，不是神社点位，不标图。'if status=='source_map_viewport'else'来源实际公布的地图参考点，非测量或导航入口。'if lat is not None else'未取得来源实际公布的经纬度；不将地址查询地图转为估算点。',
                'address_status':'legacy_only'if historical and not a.get('address')and old_address else'published','legacy_address':old_address}],
            'facts':facts,'note':note,'noteSources':[ref],'checked':DATE,'media':[],
            'record_status':'historical_directory'if historical else'directory_imported',
            'availability':{'kami':'published'if groups else'not_published','history':'not_independently_researched'},
            'source_fields':{'kami_verbatim':raw,'historical_kami_verbatim':(legacy.get('kami_verbatim')or'')if legacy else raw if historical else'',
                'former_rank':a.get('rank')or'','source_address_current':a.get('address')or'','source_address_historical':old_address or''},
            'directory':{'number':('H-'if historical else'A-')+source_identity,'display_number':f'{code:02d}-{len(rows)+1:05d}','index_name':a['name'],
                'index_url':a.get('index_url')or a['profile_url'],'listed_address':address,'original_detail_url':a.get('profile_url'),
                'detail_url':a.get('profile_url'),'detail_status':'result_link_not_individually_fetched'if historical else'published_agency_record',
                'checked':DATE,'source_sha256':a.get('source_sha256')or a.get('source_row_sha256')},
            'provenance':{'agency_source_id':None if historical else source_identity,'national_source_id':source_identity if historical else legacy['source_id']if legacy else None,
                'identity_match':'unique_name_address'if legacy else'not_merged','historical_only':historical,
                'address_precision':a.get('address_precision'),'source_vintage':vintage,'coordinate_kind':a.get('coordinate_kind'),
                'source_field_anomalies':a.get('source_field_anomalies')}}
        row['provenance']['source_fields']=row['source_fields'];rows.append(row)
    for i,(agency,a)in enumerate(agency_rows):make(a,agency,False,old[pairs[i]]if i in pairs else None)
    for i,a in enumerate(old):
        if i not in used_old:
            if office(a['name']):excluded.append({'provider':'神社史研究会','source_id':a['source_id'],'reason':'机构办公室，不作为神社实体导入'})
            else:make(a,None,True)
    # Potential duplicates remain visible and flagged, never silently merged by name.
    by_name_city=defaultdict(list)
    for r in rows:by_name_city[(name_key(r['name']),r['municipality'])].append(r)
    for group in by_name_city.values():
        if len(group)>1 and any(r['provenance']['historical_only']for r in group)and any(not r['provenance']['historical_only']for r in group):
            for r in group:r['tags'].append('同名条目待核')
            dedup_candidates.append({'ids':[r['id']for r in group],'name':group[0]['name'],'municipality':group[0]['municipality']})
    out=ROOT/f'data/shrines/{code:02d}-{slug}';out.mkdir(parents=True,exist_ok=True);collections=[]
    for pattern in ['agency*.json','history*.json']:
        for stale in out.glob(pattern):stale.unlink()
    # Batches are stable source families; individual IDs, not filenames/order, identify records.
    for kind in ['agency','history']:
        part=[r for r in rows if r['provenance']['historical_only']==(kind=='history')]
        if part:
            for start in range(0,len(part),150):
                path=out/(kind+f'-{start//150+1:03d}.json');path.write_text(json.dumps(part[start:start+150],ensure_ascii=False,indent=2)+'\n');collections.append(str(path.relative_to(ROOT)))
    municipalities=[]
    for name,group in sorted(((name,[r for r in rows if r['municipality']==name])for name in {r['municipality']for r in rows}),key=lambda x:x[0]):
        municipalities.append({'municipality':name,'area':'全域','records':len(group),'with_deities':sum(bool(r['kami'])for r in group),
            'mapped_locations':sum(l['map_status']=='mapped'for r in group for l in r['locations']),'without_coordinates':sum(not any(l['map_status']=='mapped'for l in r['locations'])for r in group)})
    coverage={'code':code,'name':pref,'slug':slug,'checked':DATE,'scope':pref+'・机构公开资料与研究会检索名录',
        'scope_note':'按来源实际公开范围整理。历史资料与机构名录分开标示；仅将唯一同名同址记录对应，其他可能重复条目保留待核。不能据此推断现今全部实存神社或全数现址。',
        'directory_rows':len(rows),'records':len(rows),'directory_indexes':sum(len(a.get('index_urls',[]))for a in agencies)+1,
        'baseline_rows':len(old),'agency_rows':len(agency_rows),'excluded_source_rows':excluded,'matched_historical_rows':len(used_old),'historical_only_records':sum(r['provenance']['historical_only']for r in rows),
        'with_deities':sum(bool(r['kami'])for r in rows),'mapped_locations':sum(l['map_status']=='mapped'for r in rows for l in r['locations']),
        'enriched_records':0,'details_matched':0,'records_with_detail_links':sum(bool(r['directory']['detail_url'])for r in rows),'municipalities':municipalities,
        'collections':collections,'indexes':[{'label':'神社史研究会・地区检索（POST）','url':baseline['query_url'],'entries':len(old),'request':baseline['request']}]+[{'label':a['label'],'url':u,'entries':None}for a in agencies for u in a.get('index_urls',[])],
        'agency_scopes':[{k:a.get(k)for k in['provider','label','scope_note','expected_rows','pagination_complete','failures']}for a in agencies],
        'coordinate_quarantine':quarantine,'duplicate_candidates':dedup_candidates,'link_corrections':[],
        'missing_fields_summary':{'deities':sum(not r['kami']for r in rows),'unmapped_records':sum(not any(l['map_status']=='mapped'for l in r['locations'])for r in rows)}}
    path=ROOT/f'data/coverage/{code:02d}-{slug}.json';path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(coverage,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:coverage[k]for k in['code','name','records','agency_rows','historical_only_records','with_deities','mapped_locations']},ensure_ascii=False),flush=True)
    return coverage

if __name__=='__main__':
    if len(sys.argv)<4:raise SystemExit('Usage: import_prefecture.py CODE BASELINE_JSON GEOJSON [AGENCY_JSON ...]')
    import_prefecture(int(sys.argv[1]),sys.argv[2],sys.argv[4:],sys.argv[3])
