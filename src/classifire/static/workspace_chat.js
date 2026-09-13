"use strict";
(() => {
  const panel = document.getElementById("workspace-chat");
  if (!panel) return;
  const body = panel.querySelector("#workspace-chat-body"), toggle = panel.querySelector(".chat-toggle");
  const form = panel.querySelector(".chat-form"), status = panel.querySelector(".chat-status");
  const preview = panel.querySelector(".chat-preview"), send = panel.querySelector(".chat-send");
  const messages = panel.querySelector(".chat-messages"), summary = panel.querySelector(".chat-context-summary");
  const recordList = panel.querySelector(".chat-record-list"), sourceList = panel.querySelector(".chat-source-list");
  const sensitive = panel.querySelector(".chat-sensitive"), remember = panel.querySelector(".chat-remember");
  const picker = panel.querySelector(".chat-record-picker"), action = panel.querySelector(".chat-action");
  let selector;
  try { selector = JSON.parse(document.getElementById("workspace-chat-context").textContent); } catch { panel.hidden = true; return; }
  selector.ids ||= []; selector.records ||= []; selector.matches ||= []; selector.word ||= null; selector.pdf ||= null; selector.xlsx ||= null;
  let turns = [], enabled = false, ready = false, busy = false, epoch = 0, contextHash = "", controller = null, unappliedArtifacts = false;
  const prefix = `classifire-chat-v1:${panel.dataset.userId}:`, ttl = 30 * 60 * 1000;
  const bytes = value => new TextEncoder().encode(JSON.stringify(value)).length;
  const key = () => prefix + contextHash;
  function report(text, error = false) { status.textContent = text; status.dataset.error = String(error); }
  function buttons() {
    const missing=selector.action==="propose_xlsx_scope" ? !selector.xlsx : selector.action==="propose_pdf_scope" ? !selector.pdf : selector.action==="propose_scope_edits" ? !selector.ids.length : selector.action==="propose_word_scope" ? !selector.word?.locators.length : false;
    preview.disabled = busy || missing || unappliedArtifacts || selector.ids.length > 50 || selector.records.length > 20; send.disabled = !enabled || !ready || busy || missing;
  }
  function selectionLabel() {
    panel.querySelector(".chat-selection").textContent = selector.draft_id
      ? `${selector.ids.length} register record(s); saved Scope revision ${selector.revision}; ${selector.word?.locators.length || 0} Word text block(s), ${selector.word?.picture_ids.length || 0} picture(s); PDF page ${selector.pdf?.page_number || "none"}; Excel rows ${selector.xlsx?.rows.join(", ") || "none"}. Unsaved edits are excluded.`
      : `${selector.records.length} library record(s); ${selector.screen?.title || selector.screen?.name || "current workspace"}.`;
  }
  function storageRemove(name) { try { sessionStorage.removeItem(name); } catch { /* Storage is optional. */ } }
  function reset(removeStored = false) {
    if (removeStored && contextHash) storageRemove(key());
    epoch++; controller?.abort(); controller = null; turns = []; ready = false; busy = false; contextHash = "";
    messages.replaceChildren(); summary.hidden = true; recordList.replaceChildren(); sourceList.replaceChildren();
    panel.querySelector(".chat-context-sections").replaceChildren(); panel.querySelector(".chat-context pre").textContent = "";
    form.elements.consent.checked = false; buttons(); selectionLabel();
  }
  function message(role, content) {
    const item = document.createElement("div"), heading = document.createElement("strong"), text = document.createElement("span");
    item.className = `chat-message chat-message-${role}`; heading.textContent = role === "user" ? "You" : "AI advice · unverified";
    text.textContent = content; item.append(heading, text); messages.append(item);
  }
  function trimTurns() {
    let removed = false;
    while (turns.length > 6 || bytes(turns) > 24000) { turns.splice(0, 2); removed = true; }
    return removed;
  }
  function saveThread() {
    if (!remember.checked || !contextHash || !turns.length) return;
    try {
      const keys = Object.keys(sessionStorage).filter(name => name.startsWith(prefix));
      for (const name of keys) {
        try { const item = JSON.parse(sessionStorage.getItem(name)); if (!item || item.expires < Date.now()) storageRemove(name); }
        catch { storageRemove(name); }
      }
      const remaining = Object.keys(sessionStorage).filter(name => name.startsWith(prefix) && name !== key());
      while (remaining.length >= 4) storageRemove(remaining.shift());
      sessionStorage.setItem(key(), JSON.stringify({hash:contextHash, turns, expires:Date.now() + ttl}));
    } catch { report("Conversation is available on this page; browser-tab storage is unavailable."); }
  }
  function restoreThread() {
    // Only called after a fresh server-side permission check and exact context hash.
    try {
      const saved = JSON.parse(sessionStorage.getItem(key()) || "null");
      if (!saved) return;
      if (saved.hash !== contextHash || !Number.isFinite(saved.expires) || saved.expires < Date.now() || !Array.isArray(saved.turns) || saved.turns.length > 6 || saved.turns.length % 2 || bytes(saved.turns) > 24000 || !saved.turns.every((t, i) => t.role === (i % 2 ? "assistant" : "user") && typeof t.content === "string" && t.content.length > 0 && t.content.length <= 12000)) { storageRemove(key()); return; }
      turns = saved.turns; remember.checked = true; messages.replaceChildren(); turns.forEach(t => message(t.role, t.content));
    } catch { storageRemove(key()); }
  }
  function open(value) {
    body.hidden = !value; toggle.hidden = value; toggle.setAttribute("aria-expanded", String(value));
    document.body.classList.toggle("chat-docked", value && panel.classList.contains("is-docked"));
    if (value) { document.dispatchEvent(new CustomEvent("classifire:register-selection-request")); panel.querySelector(".chat-close").focus(); }
  }
  toggle.addEventListener("click", () => open(true));
  document.addEventListener("classifire:chat-open", () => open(true));
  panel.querySelector(".chat-close").addEventListener("click", () => { open(false); toggle.focus(); });
  panel.addEventListener("keydown", event => { if (event.key === "Escape") { open(false); toggle.focus(); } });
  panel.querySelector(".chat-clear").addEventListener("click", () => { reset(true); document.dispatchEvent(new CustomEvent("classifire:chat-evidence-clear")); form.elements.question.value = ""; report("Conversation cleared. Preview context to start again."); });
  const width = panel.querySelector(".chat-width"), dock = panel.querySelector(".chat-dock");
  width.addEventListener("input", () => document.documentElement.style.setProperty("--chat-panel-width", `${width.value}px`));
  dock.addEventListener("click", () => { const on = panel.classList.toggle("is-docked"); dock.setAttribute("aria-pressed", String(on)); dock.textContent = on ? "Float over workspace" : "Dock beside workspace"; document.body.classList.toggle("chat-docked", on && !body.hidden); });
  remember.addEventListener("change", () => { if (remember.checked) saveThread(); else if (contextHash) storageRemove(key()); });
  action.addEventListener("change", () => { selector.action = action.value; reset(true); report("Action changed. Preview the evidence and consent again."); });
  sensitive.addEventListener("change", () => { reset(); report("Context options changed. Preview them before sending."); });
  form.elements.prompt.addEventListener("change", () => { if (form.elements.prompt.value) form.elements.question.value = form.elements.prompt.value; });
  document.addEventListener("classifire:register-selection", event => {
    const d = event.detail || {};
    if (!selector.draft_id || d.draftId !== selector.draft_id || Number(d.revision) !== Number(selector.revision) || !Array.isArray(d.ids)) return;
    const ids = [...new Set(d.ids.filter(id => typeof id === "string"))].sort();
    if (JSON.stringify(ids) === JSON.stringify(selector.ids)) return;
    selector.ids = ids; reset(); if (ids.length > 50) { preview.disabled = true; report("Select at most 50 records.", true); }
  });
  for(const kind of ["word","pdf","xlsx"])document.addEventListener(`classifire:${kind}-selection`,event=>{
    const data=event.detail||{};
    if(!selector.draft_id||data.draftId!==selector.draft_id||JSON.stringify(selector[kind])===JSON.stringify(data[kind]))return;
    selector[kind]=data[kind];if(data[kind])for(const other of ["word","pdf","xlsx"])if(other!==kind)selector[other]=null;
    reset();report("Report selection changed. Preview it and consent before sending.");
  });
  document.getElementById("scope-editor")?.addEventListener("scope:changed", () => { reset(); report("The register contains unsaved edits. A new preview will use saved values only."); });
  document.querySelector(".register-artifacts")?.addEventListener("change", () => {
    // Only applied, server-rendered selections are context. Changing this form requires Show first.
    unappliedArtifacts = true; reset(); report("Apply the saved review selection with ‘Show saved systems and prices’, then preview it here.");
    preview.disabled = true;
  });
  document.addEventListener("classifire:register-results", event => {
    const data = event.detail || {}, parseRef = value => {
      const match = typeof value === "string" && value.match(/^([0-9a-f-]{36}):([1-9][0-9]*)$/);
      if (!match || !Number.isSafeInteger(Number(match[2]))) throw new Error("Invalid saved revision");
      return {id:match[1], revision:Number(match[2])};
    };
    if (!selector.draft_id) return;
    try {
      if (!Array.isArray(data.match_selections) || data.match_selections.length > 30) throw new Error("Invalid saved reviews");
      const matches = data.match_selections.map(value => {const ref=parseRef(value);return {match_id:ref.id,match_revision:ref.revision};});
      const estimate = data.estimate_selection ? parseRef(data.estimate_selection) : null;
      selector.matches=matches;selector.estimate=estimate ? {estimate_id:estimate.id,estimate_revision:estimate.revision} : null;
      unappliedArtifacts=false;reset();report("Saved systems or prices changed. Preview the updated selection before sending.");
    } catch {
      unappliedArtifacts=true;reset();report("Saved selections could not be verified. Reopen this register before using the assistant.",true);
    }
  });
  const kindRoutes = [[/^\/technical\/variants\/([0-9a-f-]{36})$/i,"technical_variant"],[/^\/technical\/documents\/([0-9a-f-]{36})$/i,"technical_document"],[/^\/pricing\/([0-9a-f-]{36})$/i,"pricing_record"],[/^\/products\/([0-9a-f-]{36})(?:\/edit)?$/i,"product"],[/^\/labour\/([0-9a-f-]{36})(?:\/edit)?$/i,"labour"],[/^\/releases\/([0-9a-f-]{36})$/i,"library_release"],[/^\/markups\/([0-9a-f-]{36})$/i,"markup_profile"]];
  const choices = new Map();
  document.querySelectorAll("#main-content table a[href]").forEach(link => {
    const url = new URL(link.href, location.href); if (url.origin !== location.origin) return;
    for (const [pattern, kind] of kindRoutes) {
      const match = url.pathname.match(pattern); if (!match) continue;
      const value = `${kind}:${match[1]}`;
      const label = link.textContent.trim();
      const rowLabel = /^(view|open|details)$/i.test(label) ? link.closest("tr")?.querySelector("td")?.textContent.trim() : label;
      if (!choices.has(value)) choices.set(value, {kind,id:match[1],label:`${rowLabel?.slice(0,120) || kind} (${match[1].slice(0,8)})`});
    }
  });
  selector.records.forEach(record => { const value = `${record.kind}:${record.id}`; if (!choices.has(value)) choices.set(value, {...record,label:`Selected ${record.kind.replaceAll("_"," ")} (${record.id.slice(0,8)})`}); });
  if (choices.size) {
    panel.querySelector(".chat-record-picker-label").hidden = false; panel.querySelector("#chat-picker-help").hidden = false;
    choices.forEach((record, value) => { const option = new Option(record.label, value); option.selected = selector.records.some(r => r.id === record.id && r.kind === record.kind); picker.append(option); });
    picker.addEventListener("change", () => { selector.records = [...picker.selectedOptions].map(o => { const r = choices.get(o.value); return {kind:r.kind,id:r.id}; }); reset(); if (selector.records.length > 20) { preview.disabled = true; report("Choose at most 20 library records.", true); } });
  }
  const errors = {CHAT_UNAVAILABLE:"The assistant is not enabled. Context preview and manual work remain available.",CHAT_SELECTION_INVALID:"The selection does not belong to these saved records.",CHAT_CONTEXT_CHANGED:"Saved context changed. Preview it again before sending.",CHAT_CONTEXT_TOO_LARGE:"This context is too large. Select fewer records or clear older messages.",CHAT_CONSENT_REQUIRED:"Confirm sending the previewed context first.",CHAT_PROVIDER_FAILED:"The provider could not return valid advice. No project changes were saved.",CHAT_RESPONSE_INVALID:"The response could not be verified. No project changes were saved.",CHAT_EDIT_CONFLICT:"These edits conflict with saved relationships or exceed the Draft limits. Select related records and review the proposed changes.",CHAT_INPUT_INVALID:"The selected context or conversation is not valid. Clear older messages or select fewer records."};
  async function post(action, question) {
    controller = new AbortController();
    const response = await fetch(`/workspace/assistant/${action}`, {method:"POST",credentials:"same-origin",cache:"no-store",signal:controller.signal,headers:{"Content-Type":"application/json","X-CSRF-Token":panel.dataset.csrf},body:JSON.stringify({...selector,question,turns,include_sensitive:sensitive.checked,consent:form.elements.consent.checked,context_sha256:contextHash || null})});
    if (!response.ok) { let code=""; try { code=(await response.json()).detail; } catch { /* Fixed safe fallback. */ } throw new Error(errors[code] || "Request refused. Check your session, permissions and selected records."); }
    return response.json();
  }
  function showContext(context) {
    recordList.replaceChildren(); sourceList.replaceChildren();
    panel.querySelector(".chat-context-basis").textContent = context.summary || `Saved Scope revision ${context.revision || "unavailable"}`;
    const selected = new Set(context.selected_ids || []);
    for (const record of context.records) {
      const item=document.createElement("li"), title=document.createElement("strong"), details=document.createElement("span");
      title.textContent = `${record.kind}: ${record.label || record.name || record.id}${selected.has(record.id) ? " · selected" : ""}`;
      const facts=[];
      if (record.kind === "services") facts.push(record.service_type || "Service type unknown", record.quantity == null ? "Quantity unknown" : `Quantity ${record.quantity} ${record.unit}`);
      if (record.kind === "openings") facts.push(record.substrate || "Substrate unknown",record.blank ? "Blank opening" : "",`Size ${record.width_mm ?? "unknown"} × ${record.height_mm ?? "unknown"} mm`);
      if (record.description) facts.push(record.description); if (record.state || record.status) facts.push(record.state || record.status);
      details.textContent=facts.filter(Boolean).join("; ");item.append(title,details);recordList.append(item);
    }
    const sections=panel.querySelector(".chat-context-sections");sections.replaceChildren();
    for (const section of context.sections || []) {
      const details=document.createElement("details"), title=document.createElement("summary"), content=document.createElement("pre");
      title.textContent=section.title;content.textContent=JSON.stringify(section.data,null,2);details.append(title,content);sections.append(details);
    }
    if (context.word_evidence || context.pdf_evidence || context.xlsx_evidence) {
      const xlsx=!!context.xlsx_evidence, pdf=!!context.pdf_evidence, evidence=context.xlsx_evidence || context.pdf_evidence || context.word_evidence, details=document.createElement("details"), heading=document.createElement("summary"), text=document.createElement("p");
      details.open=true; heading.textContent=`Selected ${xlsx ? "Excel" : pdf ? "PDF page" : "Word"} evidence: ${evidence.original_filename}`;
      text.textContent=xlsx ? `Worksheet ${evidence.sheet.index}: ${evidence.sheet.name}; header ${evidence.header.row}, ${evidence.blocks.length} data rows, ${evidence.pictures.length} pictures. ${evidence.omitted_sheets} sheets, ${evidence.omitted_blocks} rows and ${evidence.omitted_pictures} pictures excluded. The original XLSX is not sent; formulas are not evaluated.` : pdf ? `Page ${evidence.page.page_number}: text ${evidence.blocks.length ? "included" : "excluded"}, image ${evidence.pictures.length ? "included" : "excluded"}. ${evidence.omitted_pages} other page(s) excluded. The original PDF is not sent.` : `${evidence.blocks.length} text block(s) and ${evidence.pictures.length} picture(s) selected. ${evidence.omitted_blocks} text block(s) and ${evidence.omitted_pictures} picture(s) are excluded. The original DOCX is not sent.`;
      details.append(heading,text);
      if(xlsx){const header=document.createElement("pre");header.textContent=JSON.stringify(evidence.header,null,2);details.append(header);}
      for (const block of evidence.blocks) {
        const location=document.createElement("strong"), words=document.createElement("pre");
        location.textContent=block.locator;words.textContent=block.text;details.append(location,words);
      }
      for (const picture of evidence.pictures) {
        const figure=document.createElement("figure"), image=document.createElement("img"), caption=document.createElement("figcaption");
        image.alt=`Selected ${picture.id} at ${picture.locator}`;
        image.src=xlsx ? `/scopes/${encodeURIComponent(selector.draft_id)}/workbooks/${encodeURIComponent(evidence.source_id)}/images/${picture.sheet_index}/${encodeURIComponent(picture.id)}.png` : pdf ? `/scopes/${encodeURIComponent(selector.draft_id)}/evidence/${encodeURIComponent(evidence.source_id)}/pages/${picture.page_number}.png` : `/scopes/${encodeURIComponent(selector.draft_id)}/word/${encodeURIComponent(evidence.source_id)}/pictures/${encodeURIComponent(picture.id)}`;
        image.className="chat-evidence-image";
        image.addEventListener("error",()=>{image.hidden=true;caption.textContent="Selected picture unavailable. Refresh evidence and preview again.";ready=false;form.elements.consent.checked=false;buttons();});
        caption.textContent=`${picture.id}; ${picture.locator}. Placement does not prove which opening or service it belongs to.`;
        figure.append(image,caption);details.append(figure);
      }
      sections.append(details);
    }
    for (const source of context.source_references) {
      const item=document.createElement("li");item.textContent=`${source.source_kind || "Source"}: ${source.locator || source.page_number || source.row?.sheet || "saved reference"}; ${source.claim_status || "unverified claim"}`;sourceList.append(item);
    }
    if (!context.source_references.length) { const item=document.createElement("li");item.textContent="No source references included.";sourceList.append(item); }
    panel.querySelector(".chat-context pre").textContent=JSON.stringify(context,null,2);summary.hidden=false;
  }
  function showProposal(proposal) {
    if (!proposal) return;
    const card=document.createElement("section"), heading=document.createElement("h3"), note=document.createElement("p");
    card.className="chat-scope-proposal"; heading.textContent="Proposed Scope additions (not saved)";
    note.textContent=`${proposal.notice} Existing revision ${proposal.expected_revision} is unchanged. Check for duplicates before saving. These unsaved proposal controls are not remembered after leaving this page.`;
    card.append(heading,note);
    const names=new Map(Object.values(proposal.payload).filter(Array.isArray).flat().filter(row=>row&&typeof row==="object"&&row.id).map(row=>[row.id,row.label||row.text||row.id]));
    const fieldLabels={defect_id:"Defect",opening_ids:"Openings",plane:"Plane",substrate:"Substrate",width_mm:"Width (mm)",height_mm:"Height (mm)",blank:"Blank opening",service_type:"Service type",quantity:"Quantity",unit:"Unit",state:"Evidence state",description:"Description"};
    for (const collection of ["defects","openings","services","observations"]) {
      for (const row of proposal.additions[collection]) {
        const item=document.createElement("details"), title=document.createElement("summary"), facts=document.createElement("dl");
        title.textContent=`${collection.slice(0,-1)}: ${row.label || row.text}`; item.open=true; item.append(title);
        for (const [key,value] of Object.entries(row)) {
          if(key==="id" || key==="label" || key==="text")continue;
          const term=document.createElement("dt"), detail=document.createElement("dd");
          term.textContent=fieldLabels[key] || key.replaceAll("_"," ");
          detail.textContent=value===null || value==="" || (Array.isArray(value)&&!value.length) ? "Unknown / not linked" : typeof value==="boolean" ? (value ? "Yes" : "No") : Array.isArray(value) ? value.map(id=>names.get(id)||id).join(", ") : key==="defect_id" ? (names.get(value)||value) : String(value);
          facts.append(term,detail);
        }
        const identity=document.createElement("details"), identityTitle=document.createElement("summary"), identityValue=document.createElement("p");
        identityTitle.textContent="Record identity";identityValue.textContent=row.id;identity.append(identityTitle,identityValue);
        item.append(facts,identity);card.append(item);
      }
    }
    for (const claim of proposal.claims) {
      const text=document.createElement("p");
      text.textContent=`${names.get(claim.target_id)||claim.target_kind}: ${claim.locator}; ${claim.basis}; ${claim.image_ids.join(", ") || "no pictures"}. ${claim.quote ? `Quote: ${claim.quote}. ` : ""}${claim.rationale}`;
      card.append(text);
    }
    const findings=document.createElement("ul");
    for (const finding of proposal.findings) {const item=document.createElement("li");item.textContent=finding.message;findings.append(item);}
    card.append(findings);
    const review=document.createElement("form"), button=document.createElement("button");
    review.method="post";review.action=`/scopes/${encodeURIComponent(selector.draft_id)}/word/${encodeURIComponent(proposal.source_id)}/preview`;
    const xlsx=proposal.source_kind==="xlsx", pdf=proposal.source_kind==="pdf";
    if(xlsx){
      review.action=`/scopes/${encodeURIComponent(selector.draft_id)}/workbooks/${encodeURIComponent(proposal.source_id)}/preview`;
      const mapping=document.createElement("details"),title=document.createElement("summary"),list=document.createElement("dl");title.textContent="Proposed column mapping - review before saving";
      for(const [field,column] of Object.entries(proposal.plan.mapping)){const name=document.createElement("dt"),value=document.createElement("dd");name.textContent=field.replaceAll("_"," ");value.textContent=column===null?"Not mapped":`Column ${column}`;list.append(name,value);}
      mapping.append(title,list);card.append(mapping);
    }
    if(pdf)review.action=`/scopes/${encodeURIComponent(selector.draft_id)}/evidence/${encodeURIComponent(proposal.source_id)}/scope/preview`;
    review.className="chat-scope-review";
    const fields={csrf_token:panel.dataset.csrf,expected_revision:String(proposal.expected_revision),document_sha256:proposal.document_sha256,payload:JSON.stringify(proposal.payload),targets:JSON.stringify(proposal.targets)};
    if(xlsx)fields.plan=JSON.stringify(proposal.plan);
    if(pdf){fields.document_hash=fields.document_sha256;delete fields.document_sha256;fields.page=String(proposal.page_number);}
    for (const [name,value] of Object.entries(fields)) {const input=document.createElement("input");input.type="hidden";input.name=name;input.value=value;review.append(input);}
    button.type="submit";button.className="button button-primary";button.textContent=xlsx ? "Review proposed Excel Scope" : pdf ? "Review proposed PDF Scope" : "Review proposed Word Scope";
    review.append(button);card.append(review);messages.append(card);
  }
  function showEdits(proposal) {
    if (!proposal) return;
    const card=document.createElement("section"), heading=document.createElement("h3"), note=document.createElement("p");
    card.className="chat-scope-proposal chat-edit-proposal";heading.textContent="Proposed field changes (not saved)";
    note.textContent=`${proposal.notice} ${proposal.changed_source_claims} previously matching source claim(s) will need review. These unsaved controls are not restored from conversation history.`;
    card.append(heading,note);
    const names=new Map(Object.values(proposal.payload).filter(Array.isArray).flat().filter(row=>row&&typeof row==="object"&&row.id).map(row=>[row.id,row.label||row.text||row.id]));
    const labels={defect_id:"Defect",opening_ids:"Openings",width_mm:"Width (mm)",height_mm:"Height (mm)",blank:"Blank opening",service_type:"Service type",state:"Evidence state"};
    function value(text) { return text===null || text==="" || (Array.isArray(text)&&!text.length) ? "Unknown / not linked" : typeof text==="boolean" ? (text ? "Yes" : "No") : Array.isArray(text) ? text.map(id=>names.get(id)||id).join(", ") : names.get(text)||String(text); }
    for (const change of proposal.changes) {
      const section=document.createElement("section"), title=document.createElement("h4"), reason=document.createElement("p");
      title.textContent=`${change.kind}: ${change.label}`;reason.textContent=change.rationale;section.append(title,reason);
      for (const field of change.fields) {
        const title=document.createElement("strong"), before=document.createElement("p"), after=document.createElement("p");
        title.textContent=labels[field.field] || field.field.replaceAll("_"," ");before.textContent=`Before: ${value(field.before)}`;after.textContent=`Proposed: ${value(field.after)}`;
        section.append(title,before,after);
      }
      card.append(section);
    }
    const findings=document.createElement("ul");
    for(const finding of proposal.findings){const item=document.createElement("li");item.textContent=finding.message;findings.append(item);}card.append(findings);
    const review=document.createElement("form"), button=document.createElement("button");
    review.method="post";review.action=proposal.review_url;review.className="chat-edit-review";
    const fields={csrf_token:panel.dataset.csrf,expected_revision:String(proposal.expected_revision),payload:JSON.stringify(proposal.payload),action:"validate"};
    for(const [name,value] of Object.entries(fields)){const input=document.createElement("input");input.type="hidden";input.name=name;input.value=value;review.append(input);}
    button.type="submit";button.className="button button-primary";button.textContent="Review changes in Draft editor";review.append(button);card.append(review);messages.append(card);
  }
  preview.addEventListener("click", async () => {
    const version=epoch;busy=true;buttons();
    try { const context=await post("context","Preview saved context");if(version!==epoch)return;
      if (!/^[a-f0-9]{64}$/.test(context.context_sha256)) throw new Error("Context identity is missing.");
      if (contextHash && contextHash !== context.context_sha256) { turns=[];messages.replaceChildren();form.elements.consent.checked=false; }
      contextHash=context.context_sha256;showContext(context);ready=true;restoreThread();
      report(enabled ? "Review this preview, then send your question." : "Context is ready. The AI provider is not enabled.");
    } catch(error) { if(version===epoch){ready=false;report(error.message,true);} }
    finally { if(version===epoch){busy=false;buttons();} }
  });
  form.addEventListener("submit", async event => {
    event.preventDefault();if(!enabled||!ready||busy||!form.reportValidity())return;
    const question=form.elements.question.value.trim();if(!question)return;
    const version=epoch;busy=true;buttons();report("Waiting for advice. Project data is unchanged.");
    try {const result=await post("message",question);if(version!==epoch)return;
      if(result.context.context_sha256!==contextHash)throw new Error("Context changed. Preview it again.");
      const completeAnswer=`${result.answer}\n\nUncertainty: ${result.uncertainty.join("; ")}\nRecord references: ${result.record_ids.join(", ") || "None"}\nSource references: ${result.source_ids.join(", ") || "None"}`;
      message("user",question);message("assistant",completeAnswer);
      let trimmed=false;
      if(completeAnswer.length>12000){turns=[];storageRemove(key());trimmed=true;}
      else {turns.push({role:"user",content:question},{role:"assistant",content:completeAnswer});trimmed=trimTurns();if(!turns.length)storageRemove(key());saveThread();}
      showProposal(result.proposal);
      showEdits(result.edit_proposal);
      if(["propose_word_scope","propose_pdf_scope","propose_xlsx_scope","propose_scope_edits"].includes(selector.action)){ready=false;form.elements.consent.checked=false;}
      form.elements.question.value="";
      report(`${result.notice}${trimmed ? " Some displayed exchanges exceed the conversation window and will not be sent or remembered." : ""}`);
    }catch(error){if(version===epoch){ready=false;form.elements.consent.checked=false;report(error.message,true);}}
    finally{if(version===epoch){busy=false;buttons();}}
  });
  document.querySelectorAll('form[action="/logout"]').forEach(logout=>logout.addEventListener("submit",()=>{try{Object.keys(sessionStorage).filter(k=>k.startsWith("classifire-chat-v1:")).forEach(storageRemove);}catch{}reset();}));
  window.addEventListener("pagehide",()=>{saveThread();reset();});
  window.addEventListener("pageshow",event=>{if(event.persisted)reset();});
  selectionLabel();buttons();
  fetch("/workspace/assistant",{credentials:"same-origin",cache:"no-store"}).then(async response=>{
    if(!response.ok)throw new Error("Assistant unavailable for this session.");const info=await response.json();enabled=info.enabled===true;
    report(enabled?`OpenAI / ${info.model}. Preview context before sending.`:"AI provider not enabled. You can preview saved context and continue manual work.");buttons();
  }).catch(()=>report("Assistant unavailable for this session.",true));
})();
