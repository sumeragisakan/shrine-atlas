'use strict';
// Shared, DOM-free exploration rules. Names are compared verbatim, not merged.
const AtlasExplore = (() => {
  const project = (lat, lon) => [(lon - 122) * 80.9017, (46 - lat) * 100];
  const mapped = l => Number.isFinite(l.lat) && Number.isFinite(l.lon) && l.map_status === 'mapped';
  const inView = (l, v) => {
    if (!v || !mapped(l)) return false;
    const [x, y] = project(l.lat, l.lon);
    return x >= v.x && x <= v.x + v.w && y >= v.y && y <= v.y + v.h;
  };
  const needsReview = r => !r.kami.length || !r.locations.some(mapped) || !r.directory?.detail_url || r.tags.some(t => /待核|需辨读/.test(t));
  function filter(rows, state, { searchIndex, needle = '', viewport = true, group = true } = {}) {
    return rows.filter(r =>
      (state.pref == null || r.prefecture_code === state.pref) &&
      (!state.area || state.area === '全部' || r.area === state.area) &&
      (!state.city || state.city === '全部' || r.municipality === state.city) &&
      (!state.kami || r.kami.some(g => g.names.includes(state.kami))) &&
      (!state.rank || r.source_fields?.former_rank === state.rank) &&
      (!group || !state.group || state.group.has(r.id)) &&
      (!needle || searchIndex?.get(r.id)?.includes(needle)) &&
      (!viewport || !state.viewport || r.locations.some(l => inView(l, state.viewport))) &&
      (!state.quality || state.quality === 'all' ||
        state.quality === 'review' && needsReview(r) ||
        state.quality === 'kami' && !r.kami.length ||
        state.quality === 'unmapped' && !r.locations.some(mapped) ||
        state.quality === 'enriched' && r.record_status === 'research_enriched' ||
        state.quality === 'closed' && r.entity_registry?.state === 'closed_by_merger'));
  }
  function facets(rows, kind) {
    const counts = new Map();
    for (const r of rows) {
      const values = kind === 'kami' ? r.kami.flatMap(g => g.names) : [r.source_fields?.former_rank || ''];
      for (const name of new Set(values)) {
        if (!name || /^[\sー―－—–-]+$/.test(name)) continue;
        counts.set(name, (counts.get(name) || 0) + 1);
      }
    }
    return [...counts].map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, 'ja'));
  }
  function cities(rows) {
    const groups = new Map();
    for (const r of rows) {
      const g = groups.get(r.municipality) || { name: r.municipality, area: r.area, records: [], points: [] };
      g.records.push(r); g.points.push(...r.locations.filter(mapped).map(l => project(l.lat, l.lon)));
      groups.set(r.municipality, g);
    }
    return [...groups.values()].map(g => ({ ...g,
      center: g.points.length ? [g.points.reduce((v, p) => v + p[0], 0) / g.points.length, g.points.reduce((v, p) => v + p[1], 0) / g.points.length] : null,
      bbox: g.points.length ? [Math.min(...g.points.map(p => p[0])), Math.min(...g.points.map(p => p[1])), Math.max(...g.points.map(p => p[0])), Math.max(...g.points.map(p => p[1]))] : null
    }));
  }
  function layoutCityLabels(items, width, height) {
    const bw = width < 600 ? 80 : 94, bh = 31, placed = [];
    const blocks = [{ x: 0, y: 0, w: Math.min(width - 45, 205), h: 121 }, { x: width - 50, y: 0, w: 50, h: 90 },
      { x: 0, y: height - 61, w: width, h: 61 }, { x: width - 53, y: height - 190, w: 53, h: 190 }];
    const overlap = (a, b) => a.x < b.x + b.w + 4 && a.x + a.w + 4 > b.x && a.y < b.y + b.h + 4 && a.y + a.h + 4 > b.y;
    for (const item of [...items].sort((a, b) => a.ax - b.ax || a.ay - b.ay)) {
      const candidates = [];
      for (const dy of [0, 38, -38, 76, -76, 114, -114, 152, -152]) {
        for (const dx of [0, 85, -85, 170, -170]) candidates.push([item.ax + dx, item.ay + dy]);
      }
      for (let y = 140; y < height - 69; y += 36) for (let x = 7 + bw / 2; x < width - bw / 2; x += bw + 6) candidates.push([x, y]);
      let best;
      for (const [cx, cy] of candidates) {
        const x = Math.max(bw / 2 + 6, Math.min(width - bw / 2 - 6, cx));
        const y = Math.max(bh / 2 + 6, Math.min(height - bh / 2 - 6, cy));
        const box = { x: x - bw / 2, y: y - bh / 2, w: bw, h: bh };
        const score = placed.filter(p => overlap(box, p.box)).length * 1e6 + blocks.filter(b => overlap(box, b)).length * 1e5 + Math.hypot(x - item.ax, y - item.ay);
        if (!best || score < best.score) best = { ...item, x, y, box, score };
      }
      placed.push(best);
    }
    // A very narrow viewport can exhaust greedy placements. Use clear columns
    // as a fallback so every municipality remains an individually usable entry.
    if (placed.some((a,i) => blocks.some(b=>overlap(a.box,b)) || placed.slice(i+1).some(b => overlap(a.box,b.box)))) {
      const slots=[],cols=Math.max(1,Math.floor((width-12+4)/(bw+4)));
      for(let col=0;col<cols;col++){
        const x=cols===1?width/2:bw/2+6+col*(width-bw-12)/(cols-1);
        for(let y=bh/2+6;y<height-bh/2-6;y++){
          const box={x:x-bw/2,y:y-bh/2,w:bw,h:bh};
          if(!blocks.some(b=>overlap(box,b))&&!slots.some(s=>overlap(box,s.box)))slots.push({x,y,box});
        }
      }
      if(slots.length>=items.length)return assignCitySlots(items,slots);
    }
    return assignCitySlots(items,placed);
  }
  // Minimum-cost assignment avoids pushing the last eastern label to a free
  // slot in the west. Horizontal geography has priority over vertical offsets.
  function assignCitySlots(items,slots){
    const n=items.length,m=slots.length,u=Array(n+1).fill(0),v=Array(m+1).fill(0),p=Array(m+1).fill(0),way=Array(m+1).fill(0);
    const cost=items.map(a=>slots.map(b=>4*(a.ax-b.x)**2+(a.ay-b.y)**2));
    for(let i=1;i<=n;i++){
      p[0]=i;let j0=0;const min=Array(m+1).fill(Infinity),used=Array(m+1).fill(false);
      do{
        used[j0]=true;const i0=p[j0];let delta=Infinity,j1=0;
        for(let j=1;j<=m;j++)if(!used[j]){const current=cost[i0-1][j-1]-u[i0]-v[j];if(current<min[j]){min[j]=current;way[j]=j0;}if(min[j]<delta){delta=min[j];j1=j;}}
        for(let j=0;j<=m;j++){if(used[j]){u[p[j]]+=delta;v[j]-=delta;}else min[j]-=delta;}j0=j1;
      }while(p[j0]!==0);
      do{const j1=way[j0];p[j0]=p[j1];j0=j1;}while(j0!==0);
    }
    const result=Array(n);for(let j=1;j<=m;j++)if(p[j])result[p[j]-1]={...items[p[j]-1],x:slots[j-1].x,y:slots[j-1].y,box:slots[j-1].box};
    return result;
  }
  return { project, mapped, inView, needsReview, filter, facets, cities, layoutCityLabels };
})();
if (typeof module !== 'undefined' && module.exports) module.exports = AtlasExplore;
