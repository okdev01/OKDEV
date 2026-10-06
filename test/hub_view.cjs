const assert = require('node:assert/strict');
const view = require('../hub/web/app.js');
const mods = [
  {id:'a',name:'Işık',champion:'Ahri',category:'skins',enabled:true,installed_at:10},
  {id:'b',name:'Koyu HUD',category:'ui',author:'p1mek',enabled:false,installed_at:20},
  {id:'c',name:'Zarif',champion:'Lux',category:'skins',enabled:false,installed_at:5},
];
assert.deepEqual(view.filter(mods,{term:'isik'}).map(m=>m.id),['a']);
assert.deepEqual(view.filter(mods,{term:'P1MEK'}).map(m=>m.id),['b']);
assert.deepEqual(view.filter(mods,{category:'ui'}).map(m=>m.id),['b']);
assert.deepEqual(view.filter(mods,{status:'enabled'}).map(m=>m.id),['a']);
assert.deepEqual(view.filter(mods,{favorites:['c'],onlyFavorites:true}).map(m=>m.id),['c']);
assert.deepEqual(view.filter(mods,{sort:'recent'}).map(m=>m.id),['b','a','c']);
assert.equal(view.newer('1.10.0','1.9.0'),true);
assert.equal(view.newer('1.0.0','2.0.0'),false);
assert.equal(view.newer('1.0.0','1.0.0'),false);
assert.equal(view.newer('bad','1.0.0'),false);
assert.equal(view.newer('16.18.2.85.4133','16.18.2.85.4132'),true);
assert.equal(view.newer('16.18.2','16.18.2.0.0'),false);
assert.equal(view.newer('1.0.0.0.0.1','1.0.0'),false);
assert.equal(view.newer('1.0.9007199254740992','1.0.0'),false);
assert.equal(mods[0].id,'a');
const champs=[{id:'yi',name:'Zeraora',champion:'Master Yi',description:'Electric effects'},{id:'kai',name:'Star Guardian',champion:"Kai’Sa"}];
assert.equal(view.filter(champs,{term:'masteryi'})[0].id,'yi');
assert.equal(view.filter(champs,{term:'yi Zeraora'})[0].id,'yi');
assert.equal(view.filter(champs,{term:'kaisa'})[0].id,'kai');
assert.equal(view.filter(champs,{term:'   master   yi   '})[0].id,'yi');
assert.equal(view.filter(champs,{term:'yi nonexistent'}).length,0);
assert.equal(view.bytes(0),'0 B');
assert.equal(view.bytes(1024),'1.0 KB');
assert.equal(view.bytes(1024*1024),'1.0 MB');
assert.equal(view.bytes(1024*1024*1024),'1.0 GB');
assert.equal(view.bytes(NaN),'0 B');
console.log('25 mod library view assertions passed');
