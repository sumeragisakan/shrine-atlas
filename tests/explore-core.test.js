'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const E = require('../web/explore-core.js');
const root = path.resolve(__dirname, '..');
const catalog = JSON.parse(fs.readFileSync(path.join(root, 'data/catalog.json')));
const rows = catalog.collections.flatMap(f => JSON.parse(fs.readFileSync(path.join(root, f))));
const prefs = JSON.parse(fs.readFileSync(path.join(root, catalog.map)));
const base = {pref:31, city:'全部', area:'全部', quality:'all'};

test('named municipality entries reconcile all records, including unlocated ones', () => {
  const cities = E.cities(rows);
  assert.equal(cities.length,19);
  assert.equal(cities.reduce((n,c)=>n+c.records.length,0),824);
  assert.equal(cities.find(c=>c.name==='倉吉市').records.length,59);
  assert.equal(cities.find(c=>c.name==='日吉津村').records.length,1);
  assert(cities.every(c=>c.center?.every(Number.isFinite)));
});

test('a range includes either location of a shrine, without duplicating the shrine', () => {
  const shrine = rows.find(r=>r.id==='ogamiyama');
  assert.equal(shrine.locations.length,2);
  for(const l of shrine.locations){
    const [x,y] = E.project(l.lat,l.lon),v={x:x-.001,y:y-.001,w:.002,h:.002};
    assert.equal(E.filter([shrine],{...base,viewport:v}).length,1);
  }
});

test('missing and quarantined points stay out of range results but remain in the county list', () => {
  const missing = rows.find(r=>r.directory.number===279);
  const outside = rows.find(r=>r.directory.number===450);
  const world = {x:-10000,y:-10000,w:20000,h:20000};
  assert.equal(E.filter([missing,outside],base).length,2);
  assert.equal(E.filter([missing,outside],{...base,viewport:world}).length,0);
  assert.equal(E.filter(rows,{...base,viewport:world}).length,791);
});

test('a map scope is a snapshot; moving the map does not mutate the selected area', () => {
  const point = E.project(rows[0].locations[0].lat,rows[0].locations[0].lon);
  const view = {x:point[0]-1,y:point[1]-1,w:2,h:2};
  const state = {...base,viewport:{...view}};
  const before = E.filter(rows,state).map(r=>r.id);
  view.x += 500;
  assert.deepEqual(E.filter(rows,state).map(r=>r.id),before);
  assert.equal(E.filter(rows,{...state,viewport:view}).length,0);
});

test('deity facets count shrine records once and preserve distinct source spellings', () => {
  const sample = {kami:[{names:['素盞嗚尊','素盞嗚尊']},{names:['素盞嗚尊','素盞嗚命']}],source_fields:{former_rank:'ー'}};
  assert.deepEqual(E.facets([sample],'kami').map(f=>[f.name,f.count]).sort(),[['素盞嗚命',1],['素盞嗚尊',1]].sort());
  assert.equal(E.facets([sample],'rank').length,0);
  const expected = rows.filter(r=>r.kami.some(g=>g.names.includes('素盞嗚尊')));
  assert.equal(E.facets(rows,'kami').find(f=>f.name==='素盞嗚尊').count,expected.length);
  assert.deepEqual(E.filter(rows,{...base,kami:'素盞嗚尊'}).map(r=>r.id),expected.map(r=>r.id));
});

test('city, rank, group, and missing-data filters intersect without silently clearing each other', () => {
  const city = E.filter(rows,{...base,city:'八頭町'});
  const ids = new Set(city.filter(r=>!r.kami.length).map(r=>r.id));
  const result = E.filter(rows,{...base,city:'八頭町',quality:'kami',group:ids});
  assert.equal(result.length,6);
  assert(result.every(r=>ids.has(r.id)&&r.municipality==='八頭町'&&!r.kami.length));
  const ranked = E.filter(rows,{...base,city:'倉吉市',rank:'村社'});
  assert(ranked.length>0);
  assert(ranked.every(r=>r.municipality==='倉吉市'&&r.source_fields.former_rank==='村社'));
});

for(const [width,height]of [[900,580],[353,460],[283,500]]){
  test(`all 19 city labels fit without overlaps at ${width}px`, () => {
    const bbox=prefs.find(p=>p.id===31).bbox,ar=width/height;
    let w=Math.max(bbox[2]-bbox[0],2)*1.48,h=Math.max(bbox[3]-bbox[1],2)*1.48;
    w=Math.max(w,h*ar);h=w/ar;
    const v={x:(bbox[0]+bbox[2]-w)/2,y:(bbox[1]+bbox[3]-h)/2,w,h};
    const items=E.cities(rows).map(c=>({name:c.name,ax:(c.center[0]-v.x)/v.w*width,ay:(c.center[1]-v.y)/v.h*height}));
    const labels=E.layoutCityLabels(items,width,height);
    assert.equal(labels.length,19);
    for(let i=0;i<labels.length;i++){
      const a=labels[i].box;
      assert(a.x>=0&&a.y>=0&&a.x+a.w<=width&&a.y+a.h<=height);
      const controls={x:width-46,y:height-181,w:34,h:112};
      assert(!(a.x<controls.x+controls.w&&a.x+a.w>controls.x&&a.y<controls.y+controls.h&&a.y+a.h>controls.y),`${labels[i].name} blocks the zoom controls`);
      for(let j=i+1;j<labels.length;j++){
        const b=labels[j].box;
        assert(!(a.x<b.x+b.w&&a.x+a.w>b.x&&a.y<b.y+b.h&&a.y+a.h>b.y),`${labels[i].name} overlaps ${labels[j].name}`);
      }
    }
  });
}
