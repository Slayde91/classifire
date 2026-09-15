"use strict";
// Execute complete shipped scripts with a minimal event/DOM surface, not a browser renderer.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const assets=path.resolve(__dirname,'../../src/classifire/static');
const origin='http://127.0.0.1:8837',draft='00000000-0000-4000-8000-000000000001';
const signIn='Sign in again, then reload this workspace. Your session is no longer active.';
class Element {
 constructor(){this.nodes=new Map();this.events=new Map();this.children=[];this.dataset={};this.value='';this.checked=false;this.disabled=false;this.hidden=false;this.textContent='';this.classList={toggle:()=>false,contains:()=>false,add:()=>{}};this.style={setProperty:()=>{}};this.elements=new Proxy({},{get:(target,key)=>target[key]||=(new Element())});}
 get childNodes(){return this.children;}
 querySelector(name){if(!this.nodes.has(name))this.nodes.set(name,new Element());return this.nodes.get(name);}
 querySelectorAll(selector){
  const found=[];function visit(node){for(const child of node.children||[]){if(selector.startsWith('.')&&(child.className||'').split(' ').includes(selector.slice(1)))found.push(child);visit(child);}}visit(this);return found;
 }
 addEventListener(name,callback){this.events.set(name,callback);}
 setAttribute(){} focus(){} reportValidity(){return true;}
 append(...nodes){for(const node of nodes){node.parent=this;this.children.push(node);}}
 remove(){if(this.parent){this.parent.children=this.parent.children.filter(node=>node!==this);this.parent=null;}}
 replaceChildren(...nodes){for(const child of this.children)child.parent=null;this.children=[];this.append(...nodes);}
 async fire(name){const callback=this.events.get(name);assert.ok(callback,`Missing ${name} event`);await callback({preventDefault(){}});}
}
function response(mode,payload){
 const status=mode==='unauthorized'?401:mode==='forbidden'?403:mode==='missing'?404:mode==='known_error'?422:200;
 const login=mode==='login',html=login||mode==='html';
 const raw=html?'<!doctype html>PRIVATE-HTML-PAYLOAD':mode==='broken'?'{PRIVATE-JSON-PAYLOAD':JSON.stringify(payload);
 return {ok:status>=200&&status<300,status,redirected:login,url:origin+(login?'/login?next=/scopes/'+draft:'/response'),headers:new Headers({'Content-Type':html?'text/html; charset=utf-8':'application/json; charset=utf-8'}),async json(){return JSON.parse(raw);}};
}
async function exercise(target,mode,kind='word'){
 const panel=new Element(),section=new Element();panel.dataset={userId:'synthetic',draftId:draft,csrf:'synthetic-csrf'};section.dataset.sourceKind=kind;
 panel.querySelectorAll=name=>name==='.chat-attachments'?[section]:[];
 section.querySelector('.chat-word-sources').append(new Element());
 panel.querySelector('.chat-form').elements.question.value='Synthetic question';
 const selector={draft_id:draft,revision:3,ids:[],records:[],matches:[],screen:{name:'scopes'},action:'advice'};
 const doc={getElementById:id=>id==='workspace-chat'?panel:id==='workspace-chat-context'?{textContent:JSON.stringify(selector)}:null,querySelector:()=>null,querySelectorAll:()=>[],addEventListener(){},dispatchEvent(){},createElement:()=>new Element(),createTextNode:text=>({textContent:text}),body:new Element(),documentElement:new Element()};
 const calls=[];
 const success=target==='history'?{proposals:[]}:target==='attachments'?{draft_id:draft,max_upload_bytes:1024,can_write:false,reference:'SYNTHETIC',name:'Test',sources:[]}:target==='availability'?{enabled:true,model:'synthetic'}:{context_sha256:'a'.repeat(64),records:[],source_references:[],sections:[],selected_ids:[],summary:'Synthetic saved context'};
 const error={detail:target==='attachments'?'SCOPE_DOCX_NOT_READY':'CHAT_CONSENT_REQUIRED'};
 const context={document:doc,window:{document:doc,addEventListener(){}},location:{href:origin+'/scopes/'+draft,origin},URL,URLSearchParams,TextEncoder,AbortController,Headers,CustomEvent:class{constructor(type,options){this.type=type;this.detail=options?.detail;}},sessionStorage:{getItem:()=>null,removeItem(){},setItem(){}},fetch:async(url,options)=>{calls.push({url,options});if(mode==='network')throw new Error('PRIVATE-NETWORK-PAYLOAD');if(url==='/workspace/assistant'&&target!=='availability')return response('success',{enabled:true,model:'synthetic'});return response(mode,mode==='known_error'?error:success);}};
 const filename=target==='attachments'?'workspace_word.js':'workspace_chat.js';vm.runInNewContext(fs.readFileSync(path.join(assets,filename),'utf8'),context,{filename});
 await new Promise(setImmediate);
 if(target==='preview')await panel.querySelector('.chat-preview').fire('click');
 if(target==='history')await panel.querySelector('.chat-proposal-history').querySelector('.chat-proposal-refresh').fire('click');
 if(target==='attachments')await section.querySelector('.chat-word-refresh').fire('click');
 await new Promise(setImmediate);
 const status=target==='attachments'?section.querySelector('.chat-word-status'):target==='history'?panel.querySelector('.chat-proposal-history').querySelector('.chat-proposal-status'):panel.querySelector('.chat-status');
 assert.equal(calls.length,target==='preview'||target==='history'?2:1,'No automatic retries or extra requests');
 assert.equal(panel.querySelector('.chat-form').elements.consent.checked,false,'Failure must not grant consent');
 if(target==='attachments'&&['login','unauthorized'].includes(mode))assert.equal(section.querySelector('.chat-word-sources').children.length,0,'Unauthorized source cards are cleared');
 if(target==='preview'&&mode!=='success')assert.equal(panel.querySelector('.chat-send').disabled,true);
 return {text:status.textContent,panel,section};
}
for(const target of ['availability','preview','history','attachments']){
 for(const mode of ['login','unauthorized','html','broken'])test(`${target}: ${mode} is safe and actionable`,async()=>{
  const result=await exercise(target,mode);
  if(['login','unauthorized'].includes(mode))assert.equal(result.text,signIn);
  else {assert.equal(result.text,{availability:"Assistant unavailable for this session.",preview:"Assistant response could not be verified. Preview context again.",history:"Saved proposal response could not be verified. Refresh saved proposals.",attachments:"Report response could not be verified. Refresh retained reports."}[target]);assert.doesNotMatch(result.text,/PRIVATE-|Unexpected|SyntaxError/);}
 });
 test(`${target}: valid response keeps its ordinary behavior`,async()=>{
  const result=await exercise(target,'success');
  const text={availability:/OpenAI \/ synthetic/,preview:/Review this preview/,history:/No saved proposals/,attachments:/Retained reports refreshed/}[target];assert.match(result.text,text);
 });
}
for(const kind of ['pdf','xlsx'])test(`${kind}: login redirect explains session loss`,async()=>{assert.equal((await exercise('attachments','login',kind)).text,signIn);});
test('known context refusal remains specific',async()=>{assert.equal((await exercise('preview','known_error')).text,'Confirm sending the previewed context first.');});
test('known source refusal remains specific',async()=>{assert.equal((await exercise('attachments','known_error')).text,'This report is not ready for inspection. Review its scan status.');});

test('availability network failure keeps a fixed message',async()=>{assert.equal((await exercise('availability','network')).text,'Assistant unavailable for this session.');});


for (const kind of ['word', 'pdf', 'xlsx']) {
 for (const outcome of ['forbidden', 'missing', 'malformed-error', 'success']) {
  test(`${kind}: restored attachment page ignores delayed ${outcome} body`, async () => {
   const panel = new Element(), section = new Element(), lifecycle = new Map();
   panel.dataset = {draftId: draft, csrf: 'synthetic-csrf'};
   section.dataset.sourceKind = kind;
   section.open = true;
   panel.querySelectorAll = name => name === '.chat-attachments' ? [section] : [];
   const list = section.querySelector('.chat-word-sources');
   const events = [], calls = [];
   const doc = {
    getElementById: id => id === 'workspace-chat' ? panel : null,
    addEventListener() {}, dispatchEvent(event) { events.push(event); },
    createElement: () => new Element(), createTextNode: text => ({textContent: text}),
   };
   const source = {id: 'synthetic-source', filename: `fresh.${kind}`, size_bytes: 12, status: 'pending', sha256: 'a'.repeat(64), ready: false};
   const fresh = {draft_id: draft, max_upload_bytes: 1024, can_write: true, reference: 'SYNTHETIC', name: 'Restored page', sources: [source]};
   let releaseBody, bodyStarted = false;
   const body = new Promise((resolve, reject) => { releaseBody = outcome === 'malformed-error' ? () => reject(new Error('PRIVATE-BODY')) : () => resolve(outcome === 'success' ? {...fresh, sources: []} : {detail: 'DENIED'}); });
   const context = {
    document: doc, window: {addEventListener: (name, handler) => lifecycle.set(name, handler)},
    location: {href: origin + '/scopes/' + draft, origin}, URL, URLSearchParams,
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options?.detail; } },
    fetch: async (url, options) => {
     calls.push({url, options});
     assert.equal(url, `/scopes/${draft}/assistant/${kind}`);
     if (calls.length === 1) return {
      ...response('success', {}), ok: outcome === 'success', status: outcome === 'success' ? 200 : outcome === 'missing' ? 404 : 403,
      json() { bodyStarted = true; return body; },
     };
     assert.equal(calls.length, 2, 'Old work must not trigger another request');
     return response('success', fresh);
    },
   };
   vm.runInNewContext(fs.readFileSync(path.join(assets, 'workspace_word.js'), 'utf8'), context, {filename: 'workspace_word.js'});
   const pending = section.querySelector('.chat-word-refresh').fire('click');
   await new Promise(setImmediate);
   assert.equal(bodyStarted, true, 'Old response headers arrived but its body is still pending');
   lifecycle.get('pagehide')({});
   assert.equal(list.children.length, 0);
   lifecycle.get('pageshow')({persisted: true});
   await new Promise(setImmediate);
   assert.equal(list.children.length, 1);
   const currentCard = list.children[0], currentStatus = section.querySelector('.chat-word-status').textContent;
   const selectedEvents = events.length;
   releaseBody();
   await pending;
   await new Promise(setImmediate);
   assert.equal(list.children[0], currentCard, 'An old response must not erase or replace current source cards');
   assert.equal(section.querySelector('.chat-word-status').textContent, currentStatus);
   assert.equal(section.querySelector('.chat-word-upload').querySelector('button').disabled, false);
   assert.equal(events.length, selectedEvents, 'An old response must not alter current evidence selection');
   await section.fire('toggle');
   await new Promise(setImmediate);
   assert.equal(calls.length, 2, 'The current loaded state must survive an old response');
   assert.ok(calls.every(call => !call.options.method), 'Only retained-source reads; no upload, scan or model call');
  });
 }
}


for (const kind of ['word', 'pdf', 'xlsx']) for (const mode of ['forbidden', 'missing']) {
 test(`${kind}: current ${mode} response still clears inaccessible attachment cards`, async () => {
  const result = await exercise('attachments', mode, kind);
  assert.equal(result.section.querySelector('.chat-word-sources').children.length, 0);
  assert.equal(result.section.querySelector('.chat-word-upload').querySelector('button').disabled, true);
  assert.equal(result.text, 'Request refused. Check your session, access and report scan status.');
 });
}

async function historyRace(deferLists=false){
 const panel=new Element();panel.dataset={userId:'synthetic',draftId:draft,csrf:'synthetic-csrf'};
 const selector={draft_id:draft,revision:3,ids:[],records:[],matches:[],screen:{name:'scopes'},action:'advice'};
 const doc={getElementById:id=>id==='workspace-chat'?panel:id==='workspace-chat-context'?{textContent:JSON.stringify(selector)}:null,querySelector:()=>null,querySelectorAll:()=>[],addEventListener(){},dispatchEvent(){},createElement:()=>new Element(),createTextNode:text=>({textContent:text}),body:new Element(),documentElement:new Element()};
 const pending=new Map(),calls=[];let listReads=0;
 const context={document:doc,window:{document:doc,addEventListener(){}},location:{href:origin+'/scopes/'+draft,origin},URL,URLSearchParams,TextEncoder,AbortController,Headers,CustomEvent:class{constructor(type,options){this.type=type;this.detail=options?.detail;}},sessionStorage:{getItem:()=>null,removeItem(){},setItem(){}},fetch:async(url,options)=>{
  calls.push({url,options});
  if(url==='/workspace/assistant')return response('success',{enabled:true,model:'synthetic'});
  if(url.endsWith('/native-proposals')){
   if(deferLists&&listReads++>0)return new Promise((resolve,reject)=>pending.set('list-'+listReads,{resolve,reject}));
   return response('success',{proposals:['first','second'].map(id=>({id,base_revision:3,saved_at:'synthetic'}))});
  }
  return new Promise((resolve,reject)=>pending.set(url.split('/').pop(),{resolve,reject}));
 }};
 vm.runInNewContext(fs.readFileSync(path.join(assets,'workspace_chat.js'),'utf8'),context,{filename:'workspace_chat.js'});
 await new Promise(setImmediate);
 const history=panel.querySelector('.chat-proposal-history');
 await history.querySelector('.chat-proposal-refresh').fire('click');
 const buttons=history.querySelector('.chat-proposal-list').children;
 function finish(id,failed=false,withProposal=false){
  const waiting=pending.get(id);assert.ok(waiting,'Expected an outstanding saved-proposal read');
  if(failed){waiting.reject(new Error('Synthetic delayed failure'));return;}
  const proposal=withProposal?{notice:id+' proposal',expected_revision:3,source_id:id,document_sha256:'b'.repeat(64),payload:{defects:[],openings:[],services:[],observations:[]},additions:{defects:[],openings:[],services:[],observations:[]},claims:[],findings:[],targets:[]}:undefined;
  waiting.resolve(response('success',{document:{request:{question:id+' question'},response:{answer:id+' answer',uncertainty:[],proposal},context:{context_sha256:'a'.repeat(64),records:[],source_references:[],sections:[],selected_ids:[],summary:id+' context'}},can_review:true,can_reject:withProposal,decision:null,notice:id+' notice'}));
 }
 function finishList(index,mode,ids=[]){
  const waiting=pending.get('list-'+index);assert.ok(waiting,'Expected an outstanding proposal listing');
  if(mode==='network'){waiting.reject(new Error('Synthetic old listing failure'));return;}
  waiting.resolve(response(mode,{proposals:ids.map(id=>({id,base_revision:3,saved_at:id}))}));
 }
 function finishRejection(){const waiting=pending.get('reject');assert.ok(waiting,'Expected the explicitly confirmed rejection');waiting.resolve(response('success',{id:'first',outcome:'rejected'}));}
 return {panel,history,buttons,calls,finish,finishList,finishRejection};
}
for(const failed of [false,true])test(`clearing conversation discards delayed saved-proposal ${failed?'failure':'content'}`,async()=>{
 const x=await historyRace(),opening=x.buttons[0].fire('click');
 await x.panel.querySelector('.chat-clear').fire('click');
 const historyStatus=x.history.querySelector('.chat-proposal-status').textContent;
 x.finish('first',failed);await opening;
 assert.equal(x.panel.querySelector('.chat-messages').children.length,0,'Cleared conversation must stay empty');
 assert.equal(x.panel.querySelector('.chat-context pre').textContent,'','Cleared context must stay empty');
 assert.equal(x.panel.querySelector('.chat-status').textContent,'Conversation cleared. Preview context to start again.');
 assert.equal(x.history.querySelector('.chat-proposal-status').textContent,historyStatus,'Old failures must not overwrite current status');
 assert.equal(x.panel.querySelector('.chat-form').elements.consent.checked,false);
 assert.equal(x.calls.length,3,'No model request, save, confirmation or retry');
});
test('latest saved-proposal choice wins when reads finish out of order',async()=>{
 const x=await historyRace(),first=x.buttons[0].fire('click'),second=x.buttons[1].fire('click');
 x.finish('second');await second;
 assert.equal(x.panel.querySelector('.chat-status').textContent,'second notice');
 const messages=x.panel.querySelector('.chat-messages').children.slice();
 x.finish('first');await first;
 assert.deepEqual(x.panel.querySelector('.chat-messages').children,messages);
 assert.equal(x.panel.querySelector('.chat-status').textContent,'second notice');
 assert.equal(x.panel.querySelector('.chat-form').elements.consent.checked,false);
 assert.equal(x.calls.length,4,'Only availability, listing and two explicit history reads');
});

test('earlier saved-proposal read stays hidden while the latest choice is pending',async()=>{
 const x=await historyRace(),first=x.buttons[0].fire('click'),second=x.buttons[1].fire('click');
 x.finish('first');await first;
 assert.equal(x.panel.querySelector('.chat-messages').children.length,0);
 assert.equal(x.panel.querySelector('.chat-context pre').textContent,'');
 x.finish('second');await second;
 assert.equal(x.panel.querySelector('.chat-status').textContent,'second notice');
 assert.equal(x.panel.querySelector('.chat-messages').children.length,3);
 assert.equal(x.panel.querySelector('.chat-form').elements.consent.checked,false);
 assert.equal(x.calls.length,4);
});

for(const [older,newer] of [['success','success'],['network','success'],['success','unauthorized']])test(`latest proposal listing wins over an older ${older} after ${newer}`,async()=>{
 const x=await historyRace(true),refresh=x.history.querySelector('.chat-proposal-refresh');
 const first=refresh.fire('click'),second=refresh.fire('click');
 x.finishList(3,newer,['current']);await second;
 const list=x.history.querySelector('.chat-proposal-list'),status=x.history.querySelector('.chat-proposal-status');
 if(newer==='unauthorized'){assert.equal(list.children.length,0);assert.equal(status.textContent,signIn);}
 else {assert.equal(list.children.length,1);assert.match(list.children[0].textContent,/current/);}
 const children=list.children.slice(),message=status.textContent;
 x.finishList(2,older,['stale']);await first;
 assert.deepEqual(list.children,children,'An old refresh must not replace or restore the current list');
 assert.equal(status.textContent,message,'An old refresh must not replace the current result or session warning');
 assert.equal(x.panel.querySelector('.chat-messages').children.length,0);
 assert.equal(x.panel.querySelector('.chat-form').elements.consent.checked,false);
 assert.equal(x.calls.length,4,'Only availability and three explicit list reads');
 assert.ok(x.calls.every(call=>!call.options?.method||call.options.method==='GET'),'No state-changing request');
});

for(const transition of ['stay','open another','clear'])test(`delayed rejection affects only its proposal after ${transition}`,async()=>{
 const x=await historyRace(),opening=x.buttons[0].fire('click');x.finish('first',false,true);await opening;
 const messages=x.panel.querySelector('.chat-messages'),cards=messages.querySelectorAll('.chat-scope-proposal');
 assert.equal(cards.length,1,'The first proposal offers a real generated review card');
 const firstCard=cards[0],decision=messages.querySelectorAll('.chat-proposal-decision')[0];
 const [label,button,note]=decision.children,check=label.children[0];
 assert.equal(button.disabled,true,'Rejection requires a separate explicit check');
 check.checked=true;await check.fire('change');const rejecting=button.fire('click');
 if(transition==='open another'){const next=x.buttons[1].fire('click');x.finish('second',false,true);await next;}
 if(transition==='clear')await x.panel.querySelector('.chat-clear').fire('click');
 const visible=messages.children.slice(),currentCards=messages.querySelectorAll('.chat-scope-proposal').slice();
 x.finishRejection();await rejecting;
 if(transition==='stay'){
  assert.equal(messages.querySelectorAll('.chat-scope-proposal').length,0,'Remove the rejected proposal review controls');
  assert.match(note.textContent,/Proposal rejected/);
 }else{
  assert.deepEqual(messages.children,visible,'The old rejection must not alter the current conversation');
  assert.deepEqual(messages.querySelectorAll('.chat-scope-proposal'),currentCards,'Keep the newly opened proposal review controls');
  if(transition==='open another'){assert.equal(currentCards.length,1);assert.notEqual(currentCards[0],firstCard);assert.equal(x.panel.querySelector('.chat-status').textContent,'second notice');}
  else assert.equal(visible.length,0);
 }
 const writes=x.calls.filter(call=>call.options?.method==='POST');assert.equal(writes.length,1,'Only the separately confirmed rejection may write');
 assert.ok(writes[0].url.endsWith('/native-proposals/first/reject'));
 assert.equal(writes[0].options.body.get('confirm'),'reject');
 assert.equal(writes[0].options.body.get('csrf_token'),'synthetic-csrf');
 assert.ok(x.calls.every(call=>call.url==='/workspace/assistant'||call.url.startsWith('/scopes/'+draft+'/native-proposals')),'No provider request or implicit Scope/package operation');
 assert.equal(x.panel.querySelector('.chat-form').elements.consent.checked,false);
});


test('Estimate line selection scopes preview, clears consent and never expands an empty selection', async()=>{
 const panel=new Element(),host=new Element(),ask=new Element(),events=new Map();
 const estimate='00000000-0000-4000-8000-000000000090';
 panel.dataset={userId:'synthetic',draftId:draft,csrf:'synthetic-csrf'};
 panel.querySelector('.chat-form').elements.question.value='Explain the selected prices';
 host.dataset={estimateId:estimate,estimateRevision:'4'};
 const boxes=Array.from({length:51},(_,index)=>({value:`00000000-0000-4000-8000-${String(index+100).padStart(12,'0')}`,checked:false,matches:()=>true,closest:()=>host}));
 host.querySelectorAll=()=>boxes.filter(box=>box.checked);
 host.querySelector=()=>ask;
 ask.closest=()=>host;
 const selector={draft_id:draft,revision:2,ids:[],records:[],matches:[],estimate:{estimate_id:estimate,estimate_revision:4},screen:{name:'estimates'},action:'advice'};
 const doc={getElementById:id=>id==='workspace-chat'?panel:id==='workspace-chat-context'?{textContent:JSON.stringify(selector)}:null,querySelector:name=>name==='.chat-estimate-selection'?host:null,querySelectorAll:()=>[],addEventListener(name,fn){events.set(name,fn);},dispatchEvent(event){events.get(event.type)?.(event);},createElement:()=>new Element(),createTextNode:text=>({textContent:text}),body:new Element(),documentElement:new Element()};
 const calls=[];
 const context={document:doc,window:{document:doc,addEventListener(){}},location:{href:origin+'/scopes/'+draft,origin},URL,URLSearchParams,TextEncoder,AbortController,Headers,CustomEvent:class{constructor(type,options){this.type=type;this.detail=options?.detail;}},sessionStorage:{getItem:()=>null,removeItem(){},setItem(){}},fetch:async(url,options)=>{
  calls.push({url,options});
  if(url==='/workspace/assistant')return response('success',{enabled:true,model:'synthetic'});
  assert.equal(url,'/workspace/assistant/context','This journey only previews, never calls a model or writes');
  return response('success',{context_sha256:'a'.repeat(64),records:[],source_references:[],sections:[],selected_ids:[],summary:'Synthetic selected lines'});
 }};
 vm.runInNewContext(fs.readFileSync(path.join(assets,'workspace_chat.js'),'utf8'),context,{filename:'workspace_chat.js'});
 await new Promise(setImmediate);
 const preview=panel.querySelector('.chat-preview'),form=panel.querySelector('.chat-form');
 assert.equal(ask.disabled,true);
 await preview.fire('click');
 const lastRequest=()=>JSON.parse(calls.at(-1).options.body);
 assert.deepEqual(lastRequest().estimate.line_ids,[],'No initial line choice must not disclose all prices');
 boxes[2].checked=true;boxes[0].checked=true;events.get('change')({target:boxes[0]});
 assert.equal(ask.disabled,false);
 events.get('click')({target:{closest:()=>ask}});
 assert.equal(panel.querySelector('#workspace-chat-body').hidden,false);
 await preview.fire('click');
 assert.deepEqual(lastRequest().estimate.line_ids,[boxes[0].value,boxes[2].value]);
 form.elements.consent.checked=true;
 boxes[0].checked=false;boxes[2].checked=false;events.get('change')({target:boxes[0]});
 assert.equal(form.elements.consent.checked,false);
 assert.equal(panel.querySelector('.chat-send').disabled,true);
 assert.equal(ask.disabled,true);
 await preview.fire('click');assert.deepEqual(lastRequest().estimate.line_ids,[]);
 boxes.forEach(box=>box.checked=true);events.get('change')({target:boxes[0]});
 assert.equal(preview.disabled,true);assert.equal(ask.disabled,true);
 assert.match(panel.querySelector('.chat-status').textContent,/at most 50/);
 host.dataset.estimateRevision='3';boxes.forEach(box=>box.checked=false);events.get('change')({target:boxes[0]});
 assert.equal(preview.disabled,true,'A stale revision must not replace the current selection');
 assert.ok(calls.every(call=>['/workspace/assistant','/workspace/assistant/context'].includes(call.url)));
});


for (const [route,kind,actionLabel,code] of [
 ['products','product','Edit / revise','SYN-PRODUCT-A'],
 ['labour','labour','Edit / revise','SYN-LABOUR-A'],
 ['pricing','pricing_record','View / revise','SYN-RATE-A'],
 ['technical/variants','technical_variant','View','SYN-VARIANT-A'],
]) test(`library picker identifies ${kind} by its visible record code`, async()=>{
 const panel=new Element(),picker=panel.querySelector('.chat-record-picker');
 panel.dataset={userId:'synthetic',csrf:'synthetic-csrf'};
 const first='00000000-0000-4000-8000-000000000101',second='00000000-0000-4000-8000-000000000102';
 const link=(id,label,host=origin)=>({href:host+'/'+route+'/'+id+(route==='products'||route==='labour'?'/edit':''),textContent:actionLabel,closest:()=>({querySelector:()=>({textContent:label})})});
 const links=[link(first,code),link(second,code.replace(/A$/,'B')),link(first,code),link(first,'EXTERNAL','https://unrelated.example.test')];
 const selector={ids:[],records:[],matches:[],screen:{name:route.split('/')[0]},action:'advice'};
 const doc={getElementById:id=>id==='workspace-chat'?panel:id==='workspace-chat-context'?{textContent:JSON.stringify(selector)}:null,querySelector:()=>null,querySelectorAll:name=>name==='#main-content table a[href]'?links:[],addEventListener(){},dispatchEvent(){},createElement:()=>new Element(),createTextNode:text=>({textContent:text}),body:new Element(),documentElement:new Element()};
 const calls=[];
 const context={document:doc,window:{document:doc,addEventListener(){}},location:{href:origin+'/'+route,origin},Option:class{constructor(text,value){this.textContent=text;this.value=value;this.selected=false;}},URL,URLSearchParams,TextEncoder,AbortController,Headers,CustomEvent:class{constructor(type,options){this.type=type;this.detail=options?.detail;}},sessionStorage:{getItem:()=>null,removeItem(){},setItem(){}},fetch:async(url,options)=>{
  calls.push({url,options});
  if(url==='/workspace/assistant')return response('success',{enabled:false,model:null});
  assert.equal(url,'/workspace/assistant/context');
  return response('success',{context_sha256:'a'.repeat(64),records:[],source_references:[],sections:[],selected_ids:[],summary:'Synthetic library context'});
 }};
 vm.runInNewContext(fs.readFileSync(path.join(assets,'workspace_chat.js'),'utf8'),context,{filename:'workspace_chat.js'});
 await new Promise(setImmediate);
 assert.equal(picker.children.length,2,'Duplicate and foreign-host links do not add choices');
 assert.equal(picker.children[0].textContent,code+' ('+first.slice(0,8)+')');
 assert.equal(picker.children[1].textContent,code.replace(/A$/,'B')+' ('+second.slice(0,8)+')');
 assert.ok(picker.children.every(option=>!option.selected),'Listing must not select all records');
 picker.selectedOptions=[picker.children[1]];
 const form=panel.querySelector('.chat-form');form.elements.consent.checked=true;
 await picker.fire('change');assert.equal(form.elements.consent.checked,false);
 await panel.querySelector('.chat-preview').fire('click');
 const body=JSON.parse(calls.at(-1).options.body);
 assert.deepEqual(body.records,[{kind,id:second}]);
 assert.ok(!JSON.stringify(body).includes(code),'DOM labels are display-only, not trusted context');
 assert.equal(calls.length,2,'Only availability and explicit preview; no provider or write');
});
