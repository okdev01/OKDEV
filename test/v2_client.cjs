'use strict';
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm'), assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
for (const plugin of ['OKDEV-CustomSkinSelector', 'OKDEV-CustomWheel']) {
  const source = fs.readFileSync(path.join(root, 'Pengu Loader/plugins', plugin, 'index.js'), 'utf8');
  const fn = name => { const start = source.indexOf('  function '+name+'('); assert(start >= 0); return source.slice(start, source.indexOf('\n  function ', start + 1)); };
  const sent = [];
  let visibleSkin = 103001;
  const context = { getCurrentSkinContext:()=>({championId:103, skinId:visibleSkin}), selectedModId:null,
    selectedModSkinId:null, pendingSelectionRequest:null, modsForCurrentSkin:[], modsForKey:null, panel:null,
    panelButtonRef:null, scanSkinSelection(){}, createSelectionRequestId:()=>'test', bridge:{send:p=>sent.push(p)},
    latestSkinModsRequestId:null, hideEmptyCategories:false, applyVisibleCategoryState(){}, currentSkinData:null,
    currentSkinMods:[], refreshButtonBadgeFromSelections(){}, refreshSummaryValues(){}, isOpen:false,
    sendSkinModSelection:p=>sent.push(p), sendDeselect:p=>sent.push(p), closePanel(){}};
  vm.createContext(context);
  const names = plugin.endsWith('Selector') ? ['normalizeModId','isModAvailableForSkin','sendSelect','handleModsResponse'] : ['handleModsResponse'];
  vm.runInContext(names.map(fn).join('\n'), context);
  const mod = {relativePath:'skins/103000/sample', modName:'Sample', skinId:103001, targetSkinIds:[103001,103002], availableForRequestedSkin:true};
  const response = {type:'skin-mods-response', championId:103, skinId:visibleSkin, mods:[mod], historicMod:mod.relativePath,
    selectionAuthoritative:true, selection:{relativePath:mod.relativePath,skinId:103002}, compatibleSkinIds:[103001]};
  const receive = data => context.handleModsResponse({detail:data});
  receive(response);
  assert.equal(sent.length,0,plugin+': automatic restoration must not mutate target');
  assert.equal(context.selectedModId,null);
  visibleSkin = 103002;
  receive({...response, skinId:visibleSkin, compatibleSkinIds:[visibleSkin]});
  assert.equal(context.selectedModId,mod.relativePath);
  assert.equal(context.selectedModSkinId,103002);
  assert.equal(sent.length,0);
  receive({...response, skinId:visibleSkin, selection:null, historicMod:null});
  assert.equal(context.selectedModId,null,plugin+': disabled selection is reflected locally');
  assert.equal(sent.length,0);
  if (plugin.endsWith('Selector')) {
    context.sendSelect(mod.relativePath, mod);
    assert.equal(sent.length,1,'Explicit user selection must still reach backend');
    assert.equal(sent[0].skinId,103002);
  }
  console.log(plugin+': profile target, hover, disable and explicit selection passed');
}

{
  const source=fs.readFileSync(path.join(root,'Pengu Loader/plugins/OKDEV-CustomWheel/index.js'),'utf8');
  const fn=name=>{const start=source.indexOf('  function '+name+'(');assert(start>=0);return source.slice(start,source.indexOf('\n  function ',start+1));};
  const sent=[],errors=[];
  const context={selectedMapId:'maps/old',selectedFontId:'fonts/old',selectedAnnouncerId:'announcers/old',
    selectedCategoryIds:{ui:['ui/old'],vfx:['vfx/old']},OTHER_CATEGORY_TABS:[{id:'ui'},{id:'vfx'}],
    lastCategoryModsById:{},lastMapsList:[],lastFontsList:[],lastAnnouncersList:[],emittedHistoricSelectionKeys:new Set(),
    bridge:{send:p=>sent.push(p)},refreshSummaryValues(){},refreshButtonBadgeFromSelections(){},applyVisibleCategoryState(){},
    isOpen:false,rightPaneMode:'picker',activeTab:'ui',panel:null,showSelectionError:message=>errors.push(message)};
  vm.createContext(context);
  vm.runInContext(['normalizePathLike','getSelectedIdsForCategory','handleMapsResponse','handleFontsResponse','handleAnnouncersResponse','handleCategoryModsResponse','handleCategorySelectionResult'].map(fn).join('\n'),context);
  for(const [plural,singular] of [['maps','Map'],['fonts','Font'],['announcers','Announcer']]) {
    const receive=context['handle'+plural[0].toUpperCase()+plural.slice(1)+'Response'];
    const response={type:plural+'-response',selectionAuthoritative:true,historicMod:plural+'/new',[plural]:[{id:plural+'/old'},{id:plural+'/new'}]};
    receive({detail:response});assert.equal(context['selected'+singular+'Id'],plural+'/new');
    receive({detail:{...response,historicMod:null}});assert.equal(context['selected'+singular+'Id'],null);
  }
  context.handleCategoryModsResponse({detail:{type:'category-mods-response',category:'ui',selectionAuthoritative:true,mods:[{id:'ui/new'}],historicMod:['ui/new']}});
  assert.equal(JSON.stringify(context.selectedCategoryIds.ui),'["ui/new"]');
  context.handleCategoryModsResponse({detail:{type:'category-mods-response',category:'ui',selectionAuthoritative:true,mods:[{id:'ui/new'}],historicMod:null}});
  assert.equal(context.selectedCategoryIds.ui.length,0);
  assert.equal(sent.length,0,'Reading authoritative selection must never issue another selection write');
  context.handleCategorySelectionResult({type:'category-selection-result',success:false,error:'Disk full',selected:{ui:['ui/current'],vfx:['vfx/old']}});
  assert.equal(JSON.stringify(context.selectedCategoryIds.ui),'["ui/current"]');
  assert.equal(JSON.stringify(context.selectedCategoryIds.vfx),'["vfx/old"]');
  assert.equal(errors.at(-1),'Disk full');
  console.log('Category selections: map/font/announcer refresh, HUD exclusivity, disabled state and failed-save recovery passed');
}
