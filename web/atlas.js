'use strict';
function initializeAtlas(SHRINES, PREFS, COVERAGE) {
const $=id=>document.getElementById(id), NS='http://www.w3.org/2000/svg';
const stage=$('mapStage'),svg=$('mapSvg'),markerLayer=$('markerLayer'),detail=$('detailDialog');
const state={pref:31,area:'全部',query:'',selected:null,view:null,city:'全部',quality:'all',page:0,group:null,groupLabel:'',viewport:null,kami:'',rank:'',preview:null};
let animation=0,drag=null,moved=false,toastTimer;
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const normal=s=>String(s).normalize('NFKC').replace(/[\s・·()（）／/]/g,'').replace(/國/g,'国').replace(/鸟/g,'鳥').replace(/县/g,'県').replace(/仓/g,'倉').replace(/贺/g,'賀').replace(/汤/g,'湯').replace(/滨/g,'浜').replace(/兔/g,'兎').replace(/姬/g,'姫').replace(/宫/g,'宮').replace(/满/g,'満').replace(/长/g,'長').replace(/圣/g,'聖').replace(/叶/g,'葉').replace(/贵/g,'貴').replace(/别/g,'別').replace(/斋/g,'斎').replace(/头/g,'頭').replace(/樱/g,'桜').replace(/荣/g,'栄').replace(/护/g,'護').toLowerCase();
const {project,mapped}=AtlasExplore;
const refs=(r,ids)=>ids.map(i=>`<a class="source-ref" href="${esc(r.sources[i].url)}" target="_blank" rel="noopener noreferrer" title="${esc(r.sources[i].label)}">[${i+1}]</a>`).join('');
const PAGE_SIZE=50;
const CITY_INDEX=new Map(AtlasExplore.cities(SHRINES.filter(r=>r.prefecture_code===31)).map(c=>[c.name,c]));
const KAMI_FACETS=AtlasExplore.facets(SHRINES,'kami'),RANK_FACETS=AtlasExplore.facets(SHRINES,'rank');
const searchIndex=new Map(SHRINES.map(r=>[r.id,normal([r.name,r.kana,r.municipality,r.headline,r.directory?.number,...r.aliases,...r.kami.flatMap(g=>g.names),...r.locations.map(l=>l.address)].join(' '))]));
function matching(options={}){return AtlasExplore.filter(SHRINES,state,{searchIndex,needle:normal(state.query),...options});}
function resetFilters(){Object.assign(state,{query:'',area:'全部',city:'全部',quality:'all',page:0,group:null,groupLabel:'',viewport:null,kami:'',rank:''});$('search').value='';closePreview();updateFilterButtons();}
function fitResults(){const points=matching({viewport:false}).flatMap(r=>r.locations.filter(mapped).map(l=>project(l.lat,l.lon)));if(points.length)setView(paddedBox(bboxOfPoints(points),1.5),true);else {const city=CITY_INDEX.get(state.city);setView(city?.bbox?paddedBox(city.bbox,1.6):defaultView(),true);toast('这些记录尚无可标示的参考坐标，地址仍保留在目录中');}}
function refreshResults(fit=false){state.page=0;state.group=null;state.groupLabel='';closePreview();updateFilterButtons();renderList();$('shrineList').scrollTop=0;if(fit)fitResults();else paintView();}
function selectCity(name){if(state.pref!==31)selectPref(31,false);state.city=name;state.area='全部';state.viewport=null;refreshResults(true);}
function cityOverview(){const p=PREFS.find(p=>p.id===31);return state.pref===31&&state.city==='全部'&&!state.group&&state.view.w>=(p.bbox[2]-p.bbox[0])*.98;}
function updateMapChrome(){
 const rows=matching({viewport:false}),inRange=rows.filter(r=>r.locations.some(l=>AtlasExplore.inView(l,state.view))).length;
 $('browseRange').textContent=(state.viewport?'更新此区域':'浏览当前地图范围')+` · ${inRange}社`;
 $('browseRange').disabled=!rows.length;$('countyBtn').classList.toggle('hide',state.pref!==31);
 const changed=state.viewport&&['x','y','w','h'].some(k=>Math.abs(state.viewport[k]-state.view[k])>state.view.w*.002);
 $('rangeMoved').classList.toggle('hide',!changed);
 const overview=cityOverview(),p=PREFS.find(p=>p.id===state.pref);
 $('mapTitle').textContent=state.city!=='全部'?state.city:p?p.name:'日本';
 $('mapRoman').textContent=state.city!=='全部'?'MUNICIPALITY / SHRINE DIRECTORY':state.pref===31?'TOTTORI PREFECTURE':state.pref===null?'JAPAN / 47 PREFECTURES':'COLLECTION PENDING';
 $('mapCaption').innerHTML=state.pref===31?(overview?'先选一个市町村，开始探索<br>入口位置示意 · 按名录归属统计':'点击数字，先预览这组神社<br>放大后悬停或选中可查看名称'):state.pref===null?'点击都道府县，聚焦地区<br>目前收录：鸟取县':'尚未收录神社资料';
 $('mapLevel').textContent=overview?'全县概览 · 市町村入口':state.city!=='全部'?state.city+' · 神社地点':state.view.w>450?'全国概览':'局部浏览 · 神社地点';
 $('legendText').textContent=overview?'市町村入口 · 数字为名录条数':'地点 · 数字为聚合地点数';
}
function closePreview(restore=false){state.preview=null;$('clusterPreview').hidden=true;if(restore)stage.focus({preventScroll:true});}
function previewCluster(group){
 cancelAnimationFrame(animation);const records=[...new Map(group.map(p=>[p.r.id,p.r])).values()];state.preview={group,records};
 $('previewTitle').textContent=`${records.length}条神社记录 · ${group.length}处地点`;
 $('previewPlaces').textContent=[...new Set(records.map(r=>r.municipality))].join(' / ');
 $('previewList').innerHTML=records.slice(0,4).map(r=>`<button class="preview-record" data-preview-shrine="${esc(r.id)}"><strong lang="ja">${esc(r.name)}</strong><span>${esc(shortAddress(r))}</span><small>祭神 · ${esc(r.headline)}</small></button>`).join('');
 $('previewList').querySelectorAll('button').forEach(b=>b.onclick=()=>openShrine(b.dataset.previewShrine));
 $('previewBrowse').textContent=`浏览这组全部${records.length}条 →`;
 const box=bboxOfPoints(group.map(p=>project(p.l.lat,p.l.lon))),canZoom=(box[2]-box[0]>.005||box[3]-box[1]>.005)&&state.view.w>8.1;
 $('previewZoom').disabled=!canZoom;$('previewZoom').textContent=canZoom?'放大这个区域':'同一参考点';
 $('clusterPreview').hidden=false;$('previewTitle').focus({preventScroll:true});
}
function zoomPreview(){const p=state.preview;if(!p)return;const points=p.group.map(p=>project(p.l.lat,p.l.lon)),box=bboxOfPoints(points);let v=paddedBox(box,1.8);if(v.w>state.view.w*.72){const cx=(box[0]+box[2])/2,cy=(box[1]+box[3])/2,w=state.view.w*.6,h=state.view.h*.6;v={x:cx-w/2,y:cy-h/2,w,h};}closePreview();setView(v,true);}
function shortAddress(r){return r.locations[0].address.replace(/^鳥取県/,'');}
function recordFeature(r){if(r.record_status==='research_enriched')return r.intro;const rank=r.source_fields?.former_rank;if(rank&&!/^[\sー―－—–-]+$/.test(rank))return '旧社格 · '+rank;if(r.facts.some(f=>f.nature==='来源中的文献线索'))return '由绪含文献检索线索 · 尚待核验原典';return '神社庁名录收录 · 可打开详情核对原文';}

function toast(t){$('mapStatus').textContent=t;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('mapStatus').textContent='',2600);}
function bboxOfPoints(points){return [Math.min(...points.map(p=>p[0])),Math.min(...points.map(p=>p[1])),Math.max(...points.map(p=>p[0])),Math.max(...points.map(p=>p[1]))];}
function paddedBox(b,padding=1.3){const ar=stage.clientWidth/stage.clientHeight;let w=Math.max(b[2]-b[0],2)*padding,h=Math.max(b[3]-b[1],2)*padding;w=Math.max(w,h*ar);h=w/ar;return {x:(b[0]+b[2]-w)/2,y:(b[1]+b[3]-h)/2,w,h};}
function defaultView(){if(state.pref===null)return paddedBox([70,20,2600,2210],1.07);return paddedBox(PREFS.find(p=>p.id===state.pref).bbox,state.pref===31?1.48:1.25);}
function setView(v,animate=false){cancelAnimationFrame(animation);if(!animate||!state.view||matchMedia('(prefers-reduced-motion:reduce)').matches){state.view=v;paintView();return;}const a={...state.view},start=performance.now();const tick=now=>{const t=Math.min(1,(now-start)/360),e=1-Math.pow(1-t,3);state.view=Object.fromEntries(['x','y','w','h'].map(k=>[k,a[k]+(v[k]-a[k])*e]));paintView();if(t<1)animation=requestAnimationFrame(tick);};animation=requestAnimationFrame(tick);}
function paintView(){if(!state.view)return;const v=state.view;svg.setAttribute('viewBox',`${v.x} ${v.y} ${v.w} ${v.h}`);renderMarkers();renderContext();updateMapChrome();}
function screenPoint(lat,lon){const p=project(lat,lon),v=state.view;return [(p[0]-v.x)/v.w*stage.clientWidth,(p[1]-v.y)/v.h*stage.clientHeight];}
function renderCityMarkers(rows){
 const w=stage.clientWidth,h=stage.clientHeight,counts=new Map();for(const r of rows)counts.set(r.municipality,(counts.get(r.municipality)||0)+1);
 const items=[];for(const [name,count]of counts){const city=CITY_INDEX.get(name);if(!city?.center)continue;const [wx,wy]=city.center,ax=(wx-state.view.x)/state.view.w*w,ay=(wy-state.view.y)/state.view.h*h;if(ax<-20||ay<-20||ax>w+20||ay>h+20)continue;items.push({name,count,ax,ay});}
 $('lineLayer').setAttribute('viewBox',`0 0 ${w} ${h}`);
 for(const item of AtlasExplore.layoutCityLabels(items,w,h)){
  const {name,count,x,y,ax,ay}=item;if(Math.hypot(x-ax,y-ay)>15){const line=document.createElementNS(NS,'line');for(const[k,v]of Object.entries({x1:ax,y1:ay,x2:x,y2:y}))line.setAttribute(k,v);$('lineLayer').append(line);}
  const b=document.createElement('button');b.className='city-pin';b.dataset.city=name;b.style.left=x+'px';b.style.top=y+'px';b.innerHTML=`<span lang="ja">${esc(name)}</span><b>${count}</b>`;b.setAttribute('aria-label',`探索${name}，${count}条神社记录`);b.title='按名录归属分组，点击浏览';b.onclick=()=>selectCity(name);markerLayer.append(b);
 }
}
function renderMarkers(){
 markerLayer.replaceChildren();$('lineLayer').replaceChildren();const w=stage.clientWidth,h=stage.clientHeight,rows=matching({viewport:false});if(!rows.length)return;
 if(state.view.w>450){
  const groups=new Map();for(const r of rows){const g=groups.get(r.prefecture_code)||[];g.push(r);groups.set(r.prefecture_code,g);}
  for(const [code,records]of groups){const points=records.flatMap(r=>r.locations.filter(mapped));if(!points.length)continue;const [x,y]=screenPoint(points.reduce((v,l)=>v+l.lat,0)/points.length,points.reduce((v,l)=>v+l.lon,0)/points.length);if(x<0||y<0||x>w||y>h)continue;const pref=PREFS.find(p=>p.id===code),b=document.createElement('button');b.className='pin cluster';b.style.left=x+'px';b.style.top=y+'px';b.innerHTML=`<span class="num">${records.length}</span><span>${esc(pref.name)} · ${records.length}社</span>`;b.setAttribute('aria-label',`聚焦${pref.name}${records.length}条神社记录`);b.onclick=()=>selectPref(code);markerLayer.append(b);}return;
 }
 if(cityOverview()){renderCityMarkers(rows);return;}
 const cells=new Map(),size=w<600?47:54;
 for(const r of rows)for(const l of r.locations.filter(mapped)){const [x,y]=screenPoint(l.lat,l.lon);if(x<0||y<0||x>w||y>h)continue;const key=Math.floor(x/size)+':'+Math.floor(y/size),g=cells.get(key)||[];g.push({r,l,x,y});cells.set(key,g);}
 let groups=[...cells.values()].map(points=>({points,x:points.reduce((v,p)=>v+p.x,0),y:points.reduce((v,p)=>v+p.y,0)}));
 for(let pass=0;pass<3;pass++){const merged=[];for(const g of groups){const gx=g.x/g.points.length,gy=g.y/g.points.length,near=merged.find(a=>Math.hypot(a.x/a.points.length-gx,a.y/a.points.length-gy)<38);if(near){near.points.push(...g.points);near.x+=g.x;near.y+=g.y;}else merged.push(g);}if(merged.length===groups.length)break;groups=merged;}
 for(const {points:group}of groups){
  const b=document.createElement('button'),x=group.reduce((v,p)=>v+p.x,0)/group.length,y=group.reduce((v,p)=>v+p.y,0)/group.length;b.style.left=x+'px';b.style.top=y+'px';
  if(group.length>1){const ids=[...new Set(group.map(p=>p.r.id))];b.className='pin cluster compact';b.innerHTML=`<span class="num">${group.length}</span><span>处地点</span>`;b.title=`${group.length}处地点 / ${ids.length}条神社记录，点击预览`;b.setAttribute('aria-label',b.title);b.onclick=()=>previewCluster(group);
  }else {const {r,l}=group[0];b.className='pin single compact'+(state.selected===r.id?' active':'');b.dataset.shrine=r.id;b.innerHTML=`<span class="num">·</span><span class="pin-name" lang="ja">${esc(l.label)}</span>`;b.title=`${r.name} · ${r.municipality}`;b.setAttribute('aria-label',`查看${r.name}，${r.municipality}`);b.onclick=()=>openShrine(r.id);}
  markerLayer.append(b);
 }
}

function renderContext(){const layer=$('contextLayer');layer.replaceChildren();$('gridLayer').replaceChildren();const near=state.view.w<450;if(!near)return;const labels=state.pref===31||state.pref===null?[[35.67,133.83,'日本海'],[35.14,134.03,'岡山県'],[35.36,134.55,'兵庫県'],[35.35,133.13,'島根県']]:[];for(const [lat,lon,text]of labels){const [x,y]=screenPoint(lat,lon);if(x<20||y<35||x>stage.clientWidth-20||y>stage.clientHeight-60)continue;const a=document.createElement('span');a.className='context-label';a.textContent=text;a.style.left=x+'px';a.style.top=y+'px';layer.append(a);}
 if(state.view.w<300){const v=state.view;for(let lat=34.8;lat<=36.2;lat+=.2){const y=(46-lat)*100;if(y<v.y||y>v.y+v.h)continue;const ln=document.createElementNS(NS,'line');for(const[k,val]of Object.entries({x1:v.x,x2:v.x+v.w,y1:y,y2:y}))ln.setAttribute(k,val);$('gridLayer').append(ln);}for(let lon=132.6;lon<135;lon+=.2){const x=(lon-122)*80.9017;if(x<v.x||x>v.x+v.w)continue;const ln=document.createElementNS(NS,'line');for(const[k,val]of Object.entries({x1:x,x2:x,y1:v.y,y2:v.y+v.h}))ln.setAttribute(k,val);$('gridLayer').append(ln);}}
}
function renderList(){
 const rows=matching(),base=SHRINES.filter(r=>state.pref===null||r.prefecture_code===state.pref),pref=PREFS.find(p=>p.id===state.pref),unmapped=matching({viewport:false}).filter(r=>!r.locations.some(mapped)).length;
 $('resultCount').textContent=rows.length+' 社';$('listTitle').textContent=state.city!=='全部'?state.city+'神社':state.pref===31?'鸟取县神社':state.pref===null?'已收录神社':pref.name+(base.length?'神社':' · 待收录');
 $('listHint').textContent=!base.length?'本版尚未收录该地区资料。':state.viewport?`已限定地图范围 · ${rows.length}条记录\n另有${unmapped}条符合筛选的未定位记录，不计入范围结果。`:`${rows.filter(r=>r.locations.some(mapped)).length}条可定位 · ${unmapped}条未定位\n按地点或祭神探索，无需先知道神社名。`;
 $('clearSearch').classList.toggle('hide',!state.query);$('directoryFilters').classList.toggle('hide',!base.length);$('search').disabled=!base.length;$('openExplore').classList.toggle('hide',!base.length);
 const chips=[];if(state.viewport)chips.push(['viewport','地图范围']);if(state.group)chips.push(['group',state.groupLabel||'已选聚合组']);if(state.kami)chips.push(['kami','祭神原文：'+state.kami]);if(state.rank)chips.push(['rank','旧社格：'+state.rank]);
 $('activeScopes').innerHTML=chips.map(([key,label])=>`<button data-scope="${key}" aria-label="取消${esc(label)}筛选">${esc(label)} ×</button>`).join('');$('activeScopes').classList.toggle('hide',!chips.length);
 $('activeScopes').querySelectorAll('button').forEach(b=>b.onclick=()=>{const key=b.dataset.scope;state[key]=key==='viewport'||key==='group'?null:'';state.page=0;closePreview();renderList();paintView();});
 const pages=Math.ceil(rows.length/PAGE_SIZE);state.page=Math.max(0,Math.min(state.page,pages-1));const start=state.page*PAGE_SIZE,list=$('shrineList');list.replaceChildren();
 if(!rows.length){const el=document.createElement('div');el.className='empty';el.innerHTML=!base.length?'<strong>这一页，留待继续考察。</strong>该地区尚未收录。<br><button>返回鸟取县</button>':state.viewport?'<strong>这个范围内没有匹配的已定位记录</strong>可以移动地图后更新范围，或取消范围筛选查看未定位条目。<br><button>取消地图范围</button>':'<strong>没有匹配的记录</strong>可调整市町村、资料状态或分类。<br><button>清除筛选</button>';el.querySelector('button').onclick=()=>{if(!base.length)selectPref(31);else{if(state.viewport)state.viewport=null;else resetFilters();renderList();paintView();}};list.append(el);}
 for(const r of rows.slice(start,start+PAGE_SIZE)){
  const b=document.createElement('button');b.className='record'+(state.selected===r.id?' active':'');b.dataset.shrine=r.id;b.setAttribute('aria-label',`查看${r.name}的祭神、地点与来源`);const flags=r.tags.filter(t=>/异记|待核|需辨读|未定位|未公布|法人登记/.test(t));
  b.innerHTML=`<span class="index">${r.directory.number}</span><span class="record-main"><strong lang="ja">${esc(r.name)}</strong><span class="place">${esc(shortAddress(r))}${r.locations.length>1?' · '+r.locations.length+'处地点':''}</span><span class="gods">祭神 · ${esc(r.headline)}</span><span class="discovery-note">${esc(recordFeature(r))}</span>${flags.map(t=>`<span class="flag">${esc(t)}</span>`).join(' ')}</span><span class="arrow" aria-hidden="true">›</span>`;b.onclick=()=>openShrine(r.id);list.append(b);
 }
 $('pageInfo').textContent=rows.length?`${start+1}–${Math.min(start+PAGE_SIZE,rows.length)} / ${rows.length}`:'0 / 0';$('prevPage').disabled=state.page===0;$('nextPage').disabled=state.page>=pages-1;
}
function updateFilterButtons(){document.querySelectorAll('#filters button').forEach(b=>{const active=b.dataset.area===state.area;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});$('cityFilter').value=state.city;$('qualityFilter').value=state.quality;}
function selectPref(id,animate=true){state.pref=id;resetFilters();state.selected=null;if(detail.open)detail.close();$('prefSelect').value=id===null?'all':String(id);document.querySelectorAll('.pref').forEach(p=>p.classList.toggle('selected',Number(p.dataset.pref)===id));const p=PREFS.find(p=>p.id===id);$('currentPref').textContent=p?p.name:'全国概览';renderList();setView(defaultView(),animate);}

function sourceHTML(s,i){return `<div class="source-item"><span class="source-kind">[${i+1}] ${esc(s.kind)}</span><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.label)} ↗</a><p class="domain">${esc(new URL(s.url).hostname)}</p><p>用于：${esc(s.covers)}<br>${s.published?'资料发表：'+esc(s.published)+' · ':''}本版查阅：${esc(s.checked)}</p></div>`;}
function openShrine(id,writeHash=true){
 const r=SHRINES.find(r=>r.id===id);if(!r)return;if(state.pref!==r.prefecture_code)selectPref(r.prefecture_code,false);
 closePreview();if(!matching().some(x=>x.id===id)){if(matching({viewport:false,group:false}).some(x=>x.id===id)){state.viewport=null;state.group=null;}else resetFilters();}state.selected=id;state.page=Math.floor(matching().findIndex(x=>x.id===id)/PAGE_SIZE);renderList();renderMarkers();
 $('detailTop').innerHTML=`<div class="meta">名录 #${r.directory.number} / 鳥取県 · ${esc(r.municipality)}</div><button class="detail-close" aria-label="关闭神社详情">×</button><h2 id="detailTitle" lang="ja" tabindex="-1">${esc(r.name)}</h2><div class="kana" lang="ja">${esc(r.kana||'读音未公布')}</div><div class="tags">${r.tags.map(t=>`<span class="tag">${esc(t)}</span>`).join('')}</div>`;$('detailTop').querySelector('button').onclick=()=>detail.close();
 const address=l=>`<div class="address"><strong lang="ja">${esc(l.name)}</strong>${refs(r,l.sources)}<p lang="ja">${esc(l.address)}</p>${mapped(l)?`<a class="map-link" href="https://www.openstreetmap.org/?mlat=${l.lat}&mlon=${l.lon}#map=17/${l.lat}/${l.lon}" target="_blank" rel="noopener noreferrer">在外部地图查看位置 ↗</a><div class="coord">参考坐标 ${l.lat.toFixed(6)}°N / ${l.lon.toFixed(6)}°E<br>${esc(l.precision)}</div>`:`<div class="coord">${l.map_status==='outside_prefecture_needs_review'?'来源坐标位于县界之外，暂不标图，等待核对。':'尚无已核实的参考坐标；保留地址，不估算位置。'}</div>`}</div>`;
 $('detailBody').innerHTML=`<p class="detail-intro">${esc(r.intro)}</p><h3>所在地 <span class="section-sub">${r.locations.length>1?'同一神社的不同地点':'来源记载'}</span></h3>${r.locations.map(address).join('')}<p class="source-caption">地域名录所在地：<span lang="ja">${esc(r.directory.listed_address)}</span> · <a href="${esc(r.directory.index_url)}" target="_blank" rel="noopener noreferrer">核对名录 #${r.directory.number} ↗</a></p><h3>祭神 <span class="section-sub">保留来源写法与分类</span></h3>${r.kami.length?r.kami.map(g=>`<div class="god-group"><div class="god-role">${esc(g.role)}${refs(r,g.sources)}</div><div class="god-list">${g.names.map(n=>`<span class="god" lang="ja">${esc(n)}</span>`).join('')}</div>`).join(''):'<p class="missing-notice">当前可核实来源未公布祭神，暂缺。本版没有依据社名推定主神。</p>'}${r.source_fields?.kami_verbatim?`<details class="original-table"><summary>查看神社庁祭神原栏</summary><p lang="ja">${esc(r.source_fields.kami_verbatim)}</p></details>`:''}<h3>由绪与历史线索</h3>${r.facts.map(f=>`<div class="fact"><div class="fact-title">${esc(f.label)}<span class="nature">${esc(f.nature)}</span></div><p>${esc(f.text)}${refs(r,f.sources)}</p></div>`).join('')}<div class="research-note"><strong>资料辨读</strong>${esc(r.note)}${refs(r,r.noteSources)}</div><h3>资料来源 <span class="section-sub">${r.sources.length}项 · 点击可核对原文</span></h3><p class="source-caption">查阅日期表示本版核对时间，不代表网页发表日期。机构引述的古籍尚未在本版逐条核验原卷。</p>${r.sources.map(sourceHTML).join('')}`;
 $('detailBody').scrollTop=0;if(!detail.open)detail.showModal();$('detailTitle').focus({preventScroll:true});if(writeHash){try{history.replaceState(null,'','#shrine='+r.id);}catch{}}
}

detail.addEventListener('close',()=>{try{history.replaceState(null,'',location.href.split('#')[0]);}catch{}});
detail.addEventListener('click',e=>{if(e.target===detail){const b=detail.getBoundingClientRect();if(e.clientX<b.left||e.clientX>b.right||e.clientY<b.top||e.clientY>b.bottom)detail.close();}});
function openMethod(){
 $('methodBody').innerHTML=`<h3>全县收录范围</h3><p>本版对应鳥取縣神社廳${COVERAGE.directory_indexes}个公开地域目录，共${COVERAGE.records}条记录，覆盖19个市町村；查阅日期${esc(COVERAGE.checked)}。其中${COVERAGE.with_deities}条有祭神资料，${COVERAGE.mapped_locations}处地点有可标示参考点，保留首批${COVERAGE.enriched_records}条多来源研究记录。</p><div class="notice">${esc(COVERAGE.scope_note)} 部分记录只有名录信息；由绪并未全部完成独立历史考证。</div><h3>市町村覆盖</h3><table class="coverage-table"><thead><tr><th>市町村</th><th>收录</th><th>有祭神</th><th>未定位</th></tr></thead><tbody>${COVERAGE.municipalities.map(m=>`<tr><td lang="ja">${esc(m.municipality)}</td><td>${m.records}</td><td>${m.with_deities}</td><td>${m.without_coordinates}</td></tr>`).join('')}</tbody></table><h3>如何核对</h3><ol><li>在目录中选择市町村，或用“待核对”“祭神暂缺”“未定位”筛选缺失记录。编号对应原地域目录编号；同名神社按独立条目保留。</li><li>祭神、地址、旧社格及历史线索均链接到具体来源。可以展开“祭神原栏”检查分隔与原文。未区分主配时不指定唯一主神。</li><li>新增条目以公开目录事实为基础。由绪中的古籍名称只作为检索线索，社传、原典比定与建筑年代须分开考察。</li><li>已修正${COVERAGE.link_corrections.length}处可验证的详情链接。名称或链接无法核实的详情未导入；政府法人登记关闭不等于社殿拆除或祭祀停止。</li></ol><h3>地图来源与精度</h3><p>轮廓依据国土地理院“地球地図日本”的 <a href="https://github.com/dataofjapan/land" target="_blank" rel="noopener noreferrer">GeoJSON转换版</a>进行展示简化，为旧版行政界，非测量或道路导航成果。<a href="https://www.gsi.go.jp/kankyochiri/gm_jpn.html" target="_blank" rel="noopener noreferrer">原数据说明 ↗</a>。神社位置为机构网页地图参考点，不保证是入口或社殿中心；未核实坐标不估算。全县概览显示市町村入口，数量按名录归属统计，入口位置为已定位记录的分布中心示意，不是行政中心或边界。局部圆形数字表示地点数，点击先预览，再选择放大或浏览整组。“浏览当前地图范围”只在点击时更新侧栏；移动后可再次更新。未定位条目不计入范围结果，取消范围后仍可浏览。</p><h3>本地使用与资料</h3><p>${window.ATLAS_INLINE_DATA?'本快照内嵌页面、地图和资料，可离线使用。':'主页面从独立JSON加载资料；直接双击时请打开 offline/tottori-shrine-atlas.html。'} 外部出处需联网。导出资料包含全县记录、逐项来源及覆盖报告；SQLite另存于仓库，图片与3D模型可独立扩展。</p><h3>22个地域名录</h3>${COVERAGE.indexes.map((s,i)=>sourceHTML({label:s.label+' · '+s.entries+'条',url:s.url,kind:'神社庁地域目录',covers:'名称、所在地、目录编号与详情链接',checked:COVERAGE.checked},i)).join('')}`;
 $('methodDialog').showModal();
}
$('openMethod').onclick=openMethod;$('mapSources').onclick=openMethod;$('closeMethod').onclick=()=>$('methodDialog').close();
$('exportData').onclick=()=>{const obj={title:'鸟取县神社研究地图',version:'0.4',coverage:COVERAGE,shrines:SHRINES};const url=URL.createObjectURL(new Blob([JSON.stringify(obj,null,2)],{type:'application/json;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='tottori-shrines-'+COVERAGE.checked+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('已导出 '+SHRINES.length+' 条神社资料与出处');};
$('cityFilter').innerHTML='<option value="全部">全部市町村</option>'+COVERAGE.municipalities.map(m=>`<option value="${esc(m.municipality)}">${esc(m.municipality)} · ${m.records}</option>`).join('');
$('cityFilter').onchange=e=>{if(e.target.value==='全部'){state.city='全部';state.viewport=null;refreshResults(true);}else selectCity(e.target.value);};$('qualityFilter').onchange=e=>{state.quality=e.target.value;state.viewport=null;refreshResults();};
for(const [id,delta]of [['prevPage',-1],['nextPage',1]])$(id).onclick=()=>{state.page+=delta;renderList();$('shrineList').scrollTop=0;};
$('browseRange').onclick=()=>{state.viewport={...state.view};state.page=0;closePreview();renderList();paintView();toast('已按当前地图范围更新目录');};
$('countyBtn').onclick=()=>{state.city='全部';state.area='全部';state.group=null;state.viewport=null;state.page=0;closePreview();updateFilterButtons();renderList();setView(defaultView(),true);};
$('previewClose').onclick=()=>closePreview(true);$('previewZoom').onclick=zoomPreview;
$('previewBrowse').onclick=()=>{const p=state.preview;if(!p)return;state.group=new Set(p.records.map(r=>r.id));state.groupLabel=`聚合组 · ${p.records.length}条`;state.viewport=null;state.page=0;closePreview();renderList();paintView();$('shrineList').scrollTop=0;$('listTitle').focus({preventScroll:true});if(stage.clientWidth<600)$('listTitle').scrollIntoView({behavior:'smooth',block:'start'});};
stage.addEventListener('keydown',e=>{if(e.key==='Escape'&&state.preview){e.preventDefault();closePreview(true);}});
function openExplore(){renderExplore('cities');$('exploreDialog').showModal();}
function applyFacet(kind,name){$('exploreDialog').close();selectPref(31,false);state[kind]=name;refreshResults(true);}
function renderExplore(tab){document.querySelectorAll('#exploreTabs button').forEach(b=>{b.classList.toggle('active',b.dataset.explore===tab);b.setAttribute('aria-pressed',String(b.dataset.explore===tab));});const panel=$('exploreBody');
 if(tab==='cities'){
  panel.innerHTML='<p class="explore-hint">先选一个地方。数量按名录归属统计，包含尚未定位的记录。</p>'+['东部','中部','西部'].map(area=>`<h3>${area}</h3><div class="city-cards">${COVERAGE.municipalities.filter(c=>c.area===area).map(c=>`<button data-city="${esc(c.municipality)}"><strong lang="ja">${esc(c.municipality)}</strong><span>${c.records}条记录 · ${c.without_coordinates}条未定位</span></button>`).join('')}</div>`).join('');
  panel.querySelectorAll('[data-city]').forEach(b=>b.onclick=()=>{$('exploreDialog').close();selectPref(31,false);selectCity(b.dataset.city);});
 }else if(tab==='kami'||tab==='rank'){
  const entries=tab==='kami'?KAMI_FACETS:RANK_FACETS;panel.innerHTML=`<p class="explore-hint">${tab==='kami'?'按祭神原文浏览，全县数量按神社记录去重；不同写法分别保留，不自动认定为同一神。':'按来源的旧社格原栏浏览，不作为现今重要性或等级排名；缺失项不推测。'}点击分类即可进入地图。</p>${tab==='kami'?'<label class="all-kami">浏览全部祭神写法<select id="allKami"><option value="">请选择祭神原文…</option>'+entries.map(e=>`<option value="${esc(e.name)}">${esc(e.name)} · ${e.count}社</option>`).join('')+'</select></label><h3>较多记录中出现的写法</h3>':''}<div class="facet-cards">${(tab==='kami'?entries.slice(0,18):entries).map(e=>`<button data-facet="${esc(e.name)}"><span lang="ja">${esc(e.name)}</span><b>${e.count}</b></button>`).join('')}</div>`;
  panel.querySelectorAll('[data-facet]').forEach(b=>b.onclick=()=>applyFacet(tab,b.dataset.facet));if(tab==='kami')$('allKami').onchange=e=>{if(e.target.value)applyFacet('kami',e.target.value);};
 }else{
  const records=SHRINES.filter(r=>r.record_status==='research_enriched');panel.innerHTML='<p class="explore-hint">从首批12条多来源研究记录开始阅读。选取侧重资料可查性与记载差异，供研究入门，不是全县重要性排名。</p><div class="reading-cards">'+records.map(r=>`<button data-reading="${esc(r.id)}"><small>${esc(r.municipality)} · ${r.sources.length}项来源</small><strong lang="ja">${esc(r.name)}</strong><p>${esc(r.intro)}</p><span>祭神 · ${esc(r.headline)} →</span></button>`).join('')+'</div>';panel.querySelectorAll('[data-reading]').forEach(b=>b.onclick=()=>{$('exploreDialog').close();openShrine(b.dataset.reading);});
 }
 panel.scrollTop=0;
}
$('openExplore').onclick=openExplore;$('closeExplore').onclick=()=>$('exploreDialog').close();document.querySelectorAll('#exploreTabs button').forEach(b=>b.onclick=()=>renderExplore(b.dataset.explore));

for(const p of PREFS){const count=SHRINES.filter(r=>r.prefecture_code===p.id).length;const path=document.createElementNS(NS,'path');path.setAttribute('d',p.path);path.setAttribute('class','pref'+(count?' loaded':'')+(p.id===31?' selected':''));path.dataset.pref=p.id;path.setAttribute('role','button');path.setAttribute('tabindex','0');path.setAttribute('aria-label',p.name+(count?`，已收录${count}座神社`:'，尚未收录'));const title=document.createElementNS(NS,'title');title.textContent=p.name;path.append(title);path.addEventListener('click',e=>{if(moved)return;selectPref(p.id);});path.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();selectPref(p.id);}});path.addEventListener('pointermove',e=>{if(drag)return;const b=stage.getBoundingClientRect();$('tooltip').textContent=p.name+(count?` · 已收录${count}社`:' · 尚未收录');$('tooltip').style.display='block';$('tooltip').style.transform=`translate(${Math.min(e.clientX-b.left+12,stage.clientWidth-150)}px,${Math.max(6,e.clientY-b.top-37)}px)`;});path.addEventListener('pointerleave',()=>$('tooltip').style.display='none');$('prefLayer').append(path);}
$('prefSelect').innerHTML='<option value="all">全国概览</option>'+PREFS.map(p=>`<option value="${p.id}" ${p.id===31?'selected':''}>${esc(p.name)}${SHRINES.some(r=>r.prefecture_code===p.id)?' · '+SHRINES.filter(r=>r.prefecture_code===p.id).length+' 社':''}</option>`).join('');$('prefSelect').onchange=e=>selectPref(e.target.value==='all'?null:Number(e.target.value));$('nationalBtn').onclick=()=>selectPref(null);
$('search').addEventListener('input',e=>{state.query=e.target.value;refreshResults();});$('clearSearch').onclick=()=>{state.query='';$('search').value='';refreshResults();$('search').focus();};
document.querySelectorAll('#filters button').forEach(b=>b.onclick=()=>{state.area=b.dataset.area;state.city='全部';state.viewport=null;refreshResults(true);});
function zoom(factor,cx=stage.clientWidth/2,cy=stage.clientHeight/2){closePreview();const v=state.view,nw=Math.max(8,Math.min(4000,v.w*factor)),ratio=nw/v.w;setView({x:v.x+cx/stage.clientWidth*v.w*(1-ratio),y:v.y+cy/stage.clientHeight*v.h*(1-ratio),w:nw,h:v.h*ratio});}
$('zoomIn').onclick=()=>zoom(.72);$('zoomOut').onclick=()=>zoom(1.4);$('fitView').onclick=()=>{closePreview();state.viewport=null;state.page=0;renderList();if(state.city!=='全部'||state.group||state.kami||state.rank||state.query)fitResults();else setView(defaultView(),true);};
svg.addEventListener('wheel',e=>{e.preventDefault();const b=stage.getBoundingClientRect();zoom(e.deltaY>0?1.13:.885,e.clientX-b.left,e.clientY-b.top);},{passive:false});
svg.addEventListener('pointerdown',e=>{if(e.button!==0)return;cancelAnimationFrame(animation);moved=false;drag={x:e.clientX,y:e.clientY,view:{...state.view},id:e.pointerId};});
svg.addEventListener('pointermove',e=>{if(!drag||drag.id!==e.pointerId)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.hypot(dx,dy)>5){moved=true;closePreview();svg.classList.add('dragging');$('tooltip').style.display='none';try{svg.setPointerCapture(e.pointerId);}catch{}}if(moved)setView({...drag.view,x:drag.view.x-dx/stage.clientWidth*drag.view.w,y:drag.view.y-dy/stage.clientHeight*drag.view.h});});
function endDrag(){drag=null;svg.classList.remove('dragging');setTimeout(()=>moved=false,0);}svg.addEventListener('pointerup',endDrag);svg.addEventListener('pointercancel',endDrag);window.addEventListener('pointerup',endDrag);
let resizeTimer;new ResizeObserver(()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(state.view){const v=state.view,h=v.w*stage.clientHeight/stage.clientWidth;setView({...v,y:v.y+(v.h-h)/2,h});}else setView(defaultView());},60);}).observe(stage);
selectPref(31,false);requestAnimationFrame(()=>{setView(defaultView());const m=location.hash.match(/^#shrine=([a-z0-9-]+)$/);if(m)openShrine(m[1],false);});

}
async function readJSON(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`Unable to load ${path}: HTTP ${response.status}`);
  return response.json();
}
async function bootAtlas() {
  try {
    let data = window.ATLAS_INLINE_DATA;
    if (!data) {
      const catalog = await readJSON('data/catalog.json');
      const parts = await Promise.all(catalog.collections.map(readJSON));
      data = { shrines: parts.flat(), prefectures: await readJSON(catalog.map), coverage: await readJSON(catalog.coverage) };
    }
    initializeAtlas(data.shrines, data.prefectures, data.coverage);
  } catch (error) {
    console.error(error);
    const list = document.getElementById('shrineList');
    list.replaceChildren();
    const panel = document.createElement('div'); panel.className = 'empty';
    const heading = document.createElement('strong'); heading.textContent = '需要通过本地服务器打开主页面';
    const text = document.createElement('p'); text.textContent = '在项目目录运行 python -m http.server 8000，然后访问 http://localhost:8000；也可以直接打开 offline/tottori-shrine-atlas.html。';
    const link = document.createElement('a'); link.href = 'offline/tottori-shrine-atlas.html'; link.textContent = '打开单文件离线版本 →';
    panel.append(heading, text, link); list.append(panel);
    document.getElementById('resultCount').textContent = '未加载';
  }
}
bootAtlas();
