"use strict";
// Execute complete shipped scripts with a minimal event/DOM surface, not a browser renderer.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const assets=path.resolve(__dirname,'../../src/classifire/static');
const origin='http://127.0.0.1:8837',draft='00000000-0000-4000-8000-000000000001';
const signIn='Sign in again, then reload this workspace. Your session is no longer active.';
class Element {
 constructor(){this.nodes=new Map();this.events=new Map();this.children=[];this.dataset={};this.value='';this.checked=false;this.disabled=false;this.hidden=false;this.textContent='';this.classList={toggle:()=>false,contains:()=>false,add:()=>{}};this.style={setProperty:()=>{}};this.elements=new Proxy({},{get:(target,key)=>target[key]||=(new Element())});}
 querySelector(name){if(!this.nodes.has(name))this.nodes.set(name,new Element());return this.nodes.get(name);}
 querySelectorAll(){return [];}
 addEventListener(name,callback){this.events.set(name,callback);}
 setAttribute(){} focus(){} reportValidity(){return true;}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=nodes;}
 async fire(name){const callback=this.events.get(name);assert.ok(callback,`Missing ${name} event`);await callback({preventDefault(){}});}
}
function response(mode,payload){
 const status=mode==='unauthorized'?401:mode==='known_error'?422:200;
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
