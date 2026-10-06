const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('Pengu Loader/plugins/OKDEV-PartyMode/index.js', 'utf8');
const start = source.indexOf('  const skinNames =');
const end = source.indexOf('  // Load bridge port', start);
let requests = 0;
let updates = 0;
const context = vm.createContext({
  fetch: async () => {
    requests++;
    return {ok: true, json: async () => ({skins: [
      {id: 18080, name: 'Immortalized Legend Tristana', chromas: [{id: 18081, name: 'Tristana Chroma'}]},
    ]})};
  },
  t: (text, vars) => text.replace('{id}', vars.id),
  updatePanelState: () => updates++, setTimeout,
});
vm.runInContext(source.slice(start, end) + '\nglobalThis.lookup = selectionName; globalThis.loads = championLoads;', context);
(async () => {
  const pick = {champion_id: 18, skin_id: 18080};
  assert.equal(context.lookup(pick), 'Skin: 18080');
  context.lookup(pick);
  await context.loads.get(18);
  assert.equal(requests, 1);
  assert.equal(updates, 1);
  assert.equal(context.lookup(pick), 'Immortalized Legend Tristana');
  assert.equal(context.lookup({...pick, chroma_id: 18081}), 'Tristana Chroma');
  assert.match(context.lookup({champion_id: 145, skin_id: 145070, chroma_id: 145999}), /Kai.Sa.*Form 2/);
  assert.equal(context.lookup(null), '');
  assert.equal(context.lookup({champion_id: '../../bad', skin_id: 1}), '');
  console.log('Party skin catalog lookup: PASS');
})().catch(error => { console.error(error); process.exitCode = 1; });
