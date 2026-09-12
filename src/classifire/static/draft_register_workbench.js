/* Native register authoring over the existing authenticated capability forms. */
"use strict";
(() => {
  const panel=document.getElementById("register-workbench"), scopeForm=document.getElementById("scope-editor");
  if (!panel || !scopeForm) return;
  const body=panel.querySelector("[data-workbench-body]"), status=panel.querySelector("[data-workbench-status]");
  const heading=panel.querySelector("h2"), draftId=scopeForm.dataset.draftId;
  const revision=Number(scopeForm.querySelector('[name="expected_revision"]').value);
  const base=`/scopes/${draftId}`, selectionForm=document.querySelector(".register-artifacts form");
  let row=null, capability="system", busy=false, dirty=false, currentURL="", opener=null;
  let selected={system:[...(selectionForm?.querySelector('[name="match"]')?.selectedOptions || [])].map(option=>option.value).filter(Boolean),price:selectionForm?.querySelector('[name="estimate"]')?.value || ""};
  const scopeDirty=()=>document.getElementById("scope-download").hidden;
  const message=text=>{status.textContent=text;};
  function allowed(raw,method="GET") {
    const url=new URL(raw,location.origin);
    if(url.origin!==location.origin || url.username || url.password || url.pathname.includes("%") || url.pathname.includes("\\")) throw new Error("Unsupported workspace address.");
    const prefix=base+"/", tail=url.pathname.startsWith(prefix) ? url.pathname.slice(prefix.length) : "";
    const get=/^(system-matches|estimates)(\/[a-zA-Z0-9-]+)?$/;
    const post=/^(system-matches|estimates)(\/[a-zA-Z0-9-]+(\/(review|constraints|lines)(\/[a-zA-Z0-9-]+)?)?)?$/;
    if(!(method==="POST" ? post : get).test(tail)) throw new Error("Use an explicit supported capability action.");
    return url;
  }
  function canLeave() { return !dirty || window.confirm("Discard unsaved review or price entries in this panel?"); }
  function picker(kind) { return `${base}/${kind==="system" ? "system-matches" : "estimates"}?scope_revision=${revision}`; }
  function endpoint(kind) {
    if(kind==="system")return row?.systemURL || picker(kind);
    const value=selected[kind];
    if(/^[a-zA-Z0-9-]+:[1-9][0-9]*$/.test(value)) {
      const [id,rev]=value.split(":");
      return `${base}/${kind==="system" ? "system-matches" : "estimates"}/${id}?revision=${rev}`;
    }
    return picker(kind);
  }
  function lockForms() {
    const content=body.querySelector("[data-workbench-content]");
    const otherScope=content && Number(content.dataset.scopeRevision)!==revision;
    const otherTarget=content?.dataset.capability==="system" && content.dataset.artifactId && row &&
      (content.dataset.openingId!==row.opening_id || content.dataset.serviceId!==(row.service_id || ""));
    if(scopeDirty() || otherScope || otherTarget) {
      body.querySelectorAll('form[method="post"] button,form[method="post"] input,form[method="post"] select,form[method="post"] textarea').forEach(el=>{el.disabled=true;});
      message(otherScope || otherTarget ? "This historical result belongs to another Scope revision or target. Open the matching register revision and row to edit it." : "Scope has unsaved changes. Save the Scope and reopen this row before saving a review or price. Panel entries remain visible.");
    }
  }
  function prefill(content,ok) {
    if(!ok || !row || Number(content.dataset.scopeRevision)!==revision || content.dataset.artifactId) return;
    const set=(name,value)=>{
      const field=content.querySelector(`form[method="post"] [name="${name}"]`);
      if(field && !field.value && [...(field.options || [])].some(option=>option.value===value)) field.value=value;
    };
    if(capability==="system") {
      set("opening_id",row.opening_id);set("service_id",row.service_id || "");
      for(const [name,value] of [["opening_id",row.opening_id],["service_id",row.service_id || ""]]) {
        const field=content.querySelector(`form[method="post"] [name="${name}"]`);
        if(field) [...field.options].forEach(option=>{option.disabled=option.value!==value;});
      }
    }
    // A selected review is optional; the user still explicitly starts the estimate.
  }
  function focusPriceTarget(content) {
    if(content.dataset.capability!=="price" || !row)return;
    const target=row.service_id ? `service:${row.service_id}` : `blank_opening:${row.opening_id}`;
    content.querySelectorAll("[data-estimate-target]").forEach(line=>{line.hidden=line.dataset.estimateTarget!==target;});
    const picker=content.querySelector('form[method="get"] select[name="target"]');
    if(picker) {
      const available=[...picker.options].some(option=>option.value===target);
      if(available) { picker.value=target;[...picker.options].forEach(option=>{option.disabled=option.value!==target;}); }
      else picker.closest("form").hidden=true;
    }
    if(content.dataset.artifactId) {
      const hint=document.createElement("p");hint.className="scope-hint";
      hint.textContent="Editing the selected register record only. Estimate totals include all retained lines; other records remain unchanged.";
      content.prepend(hint);
    }
  }
  async function refreshProjection(content) {
    const id=content.dataset.artifactId, rev=content.dataset.artifactRevision;
    if(!id || !/^[1-9][0-9]*$/.test(rev || "")) return;
    const kind=content.dataset.capability;
    if(!["system","price"].includes(kind)) return;
    const next={...selected,system:[...selected.system]};
    if(kind==="system") {
      const oldContext=JSON.parse(document.getElementById("scope-register-context").textContent);
      const targetKey=content.dataset.serviceId ? `opening:${content.dataset.openingId}:service:${content.dataset.serviceId}` : `blank_opening:${content.dataset.openingId}`;
      const previous=oldContext.row_targets?.[targetKey]?.match_selection;
      next.system=next.system.filter(value=>value!==previous && value!==`${id}:${rev}`);
      next.system.push(`${id}:${rev}`);
      if(next.system.length>30)throw new Error("The review was saved. Select up to 30 row reviews before updating the register or saving a package.");
    } else next.price=`${id}:${rev}`;
    const url=new URL(base,location.origin);url.searchParams.set("revision",String(revision));
    next.system.forEach(value=>url.searchParams.append("match",value));
    if(next.price)url.searchParams.set("estimate",next.price);
    const response=await fetch(url,{credentials:"same-origin",cache:"no-store"});
    if(!response.ok)throw new Error("Saved artifact is retained, but the register could not refresh. Reopen the saved revision before continuing.");
    const page=new DOMParser().parseFromString(await response.text(),"text/html");
    const contextNode=page.getElementById("scope-register-context"), remoteForm=page.querySelector(".register-artifacts form");
    if(!contextNode || !remoteForm)throw new Error("The session or register view changed. Reopen the project.");
    const context=JSON.parse(contextNode.textContent);
    if(JSON.stringify([...(context.match_selections || [])].sort())!==JSON.stringify([...next.system].sort()) || (context.estimate_selection || "")!==next.price) {
      throw new Error("Saved artifacts are retained, but the chosen register set could not be verified. Reopen the selection before continuing.");
    }
    if(kind==="system" && row && content.dataset.openingId===row.opening_id && content.dataset.serviceId===(row.service_id || "")) {
      row.systemURL=`${base}/system-matches/${id}?revision=${rev}`;
    }
    selected=next;
    for(const name of ["match","estimate"]) {
      const current=selectionForm?.querySelector(`[name="${name}"]`), remote=remoteForm.querySelector(`[name="${name}"]`);
      if(current && remote)current.replaceChildren(...[...remote.options].map(option=>option.cloneNode(true)));
    }
    document.getElementById("scope-register-context").textContent=JSON.stringify(context);
    document.dispatchEvent(new CustomEvent("classifire:register-results",{detail:context}));
    const stateURL=new URL(location.href);stateURL.search=url.search;history.replaceState(null,"",stateURL);
    scopeForm.action=url.pathname+url.search;
    const packageLink=document.querySelector("[data-register-package]"),remotePackage=page.querySelector("[data-register-package]");
    if(packageLink && remotePackage)packageLink.href=remotePackage.href;
    const reportLink=document.querySelector("[data-register-report]"),remoteReport=page.querySelector("[data-register-report]");
    if(reportLink && remoteReport)reportLink.href=remoteReport.href;
  }
  async function load(raw,{method="GET",fields=null,fromSave=false}={}) {
    if(busy)return;
    if(method==="POST" && scopeDirty()){lockForms();return;}
    let url;
    try{url=allowed(raw,method);}catch(error){message(error.message);return;}
    if(url.searchParams.has("scope_revision") && url.searchParams.get("scope_revision")!==String(revision)) {
      message("Open the desired saved Scope revision in the register before reviewing another row.");return;
    }
    busy=true;body.setAttribute("aria-busy","true");const priorInert=scopeForm.inert, priorBodyInert=body.inert;
    scopeForm.inert=true;body.inert=true;
    message(method==="POST" ? "Saving this Draft action..." : "Loading saved inputs...");
    try {
      const response=await fetch(url,{method,body:fields,credentials:"same-origin",cache:"no-store",headers:{"X-Classifire-Workspace":"register",...(method==="POST" ? {"Content-Type":"application/x-www-form-urlencoded"} : {})}});
      const finalURL=allowed(response.url,response.redirected ? "GET" : method);
      const html=await response.text();
      const page=new DOMParser().parseFromString(html,"text/html"), content=page.querySelector("[data-workbench-content]");
      if(!content || content.dataset.draftId!==draftId || content.querySelector("script") || !["system","price"].includes(content.dataset.capability)) {
        throw new Error(`The action was refused or the session changed (${response.status}). Your entries remain here; reopen the project before retrying.`);
      }
      capability=content.dataset.capability;
      const target=row?.service_id ? `service:${row.service_id}` : row?.blank ? `blank_opening:${row.opening_id}` : null;
      if(response.ok && capability==="price" && target && content.dataset.artifactId && Number(content.dataset.scopeRevision)===revision && !finalURL.searchParams.has("target")) {
        finalURL.searchParams.set("target",target);finalURL.searchParams.set("revision",content.dataset.artifactRevision);
        busy=false;scopeForm.inert=priorInert;body.inert=priorBodyInert;
        return await load(finalURL,{fromSave:fromSave || method==="POST"});
      }
      body.replaceChildren(document.importNode(content,true));currentURL=finalURL.href;
      dirty=!response.ok;prefill(body.firstElementChild,response.ok);focusPriceTarget(body.firstElementChild);
      panel.querySelectorAll("[data-workbench-tab]").forEach(button=>button.setAttribute("aria-pressed",String(button.dataset.workbenchTab===capability)));
      if(response.ok) {
        await refreshProjection(body.firstElementChild);
        message(fromSave || method==="POST" ? "Saved. The register shows the returned artifact revision; earlier values remain in history." : "Saved inputs loaded. Choose and save each action explicitly.");
      } else message(`Changes were not saved (${response.status}). Review the retained entries and errors below.`);
      lockForms();heading.focus({preventScroll:true});
    } catch(error) { message(error.message || "The action could not be verified. Reopen the saved artifact before retrying."); }
    finally {busy=false;scopeForm.inert=priorInert;body.inert=priorBodyInert;body.removeAttribute("aria-busy");}
  }
  async function open(detail) {
    if(busy || !canLeave())return;
    if(scopeDirty() || detail.modified){opener=document.activeElement;panel.hidden=false;body.replaceChildren();row=null;message("Save the Scope before opening technical or price authoring. No capability has run.");heading.focus();return;}
    if(!detail.row?.opening_id || detail.row.needsReview || panel.dataset[detail.capability]!=="true")return;
    row=detail.row;capability=detail.capability;opener=document.activeElement;dirty=false;
    panel.hidden=false;panel.querySelector("[data-workbench-target]").textContent=`${row.label || row.opening_id} / Opening ${row.opening_id}${row.service_id ? " / Service "+row.service_id : " / Blank opening"}`;
    panel.querySelectorAll("[data-workbench-tab]").forEach(button=>{button.disabled=panel.dataset[button.dataset.workbenchTab]!=="true";});
    await load(detail.savedURL || endpoint(capability));
  }
  document.addEventListener("classifire:register-author",event=>open(event.detail));
  panel.querySelector("[data-workbench-close]").addEventListener("click",()=>{if(busy || !canLeave())return;panel.hidden=true;dirty=false;
    const returnButton=row && [...document.querySelectorAll("[data-register-capability]")].find(button=>button.dataset.registerOpening===row.opening_id && button.dataset.registerService===(row.service_id || "") && button.dataset.registerCapability===capability);
    const target=opener?.isConnected ? opener : returnButton;
    if(target)target.focus();else {const grid=document.getElementById("scope-register");grid.tabIndex=-1;grid.focus();}});
  panel.querySelectorAll("[data-workbench-tab]").forEach(button=>button.addEventListener("click",()=>{
    if(busy || !row || !canLeave())return;dirty=false;capability=button.dataset.workbenchTab;load(endpoint(capability));
  }));
  body.addEventListener("input",()=>{dirty=true;});
  body.addEventListener("change",()=>{dirty=true;});
  body.addEventListener("submit",event=>{
    const form=event.target;if(!(form instanceof HTMLFormElement))return;event.preventDefault();
    if(busy)return;const method=form.method.toUpperCase(),fields=new URLSearchParams(new FormData(form));
    if(event.submitter?.name)fields.set(event.submitter.name,event.submitter.value);
    if(method==="GET") {
      if(!canLeave())return;const url=new URL(form.getAttribute("action") || currentURL,location.origin);url.search=fields.toString();dirty=false;load(url);
    } else if(method==="POST") {
      if(capability==="system" && row && fields.has("opening_id") &&
         (fields.get("opening_id")!==row.opening_id || fields.get("service_id")!==(row.service_id || ""))) {
        message("This review belongs to the selected row. Reopen the intended row before saving.");return;
      }
      load(form.getAttribute("action") || currentURL,{method,fields});
    }
  });
  body.addEventListener("click",event=>{
    const link=event.target.closest("a[href]");if(!link)return;
    try{const url=allowed(link.href);event.preventDefault();if(!busy && canLeave()){dirty=false;load(url);}}catch{ /* Explicit report/download/source links retain their existing navigation. */ }
  });
  scopeForm.addEventListener("scope:changed",()=>{if(!panel.hidden)lockForms();});
  window.addEventListener("beforeunload",event=>{if(dirty){event.preventDefault();event.returnValue="";}});
})();
