"use strict";
(() => {
  const panel = document.getElementById("workspace-chat");
  if (!panel) return;
  const body = panel.querySelector("section"), toggle = panel.querySelector(".chat-toggle");
  const form = panel.querySelector(".chat-form"), status = panel.querySelector(".chat-status");
  const preview = panel.querySelector(".chat-preview"), send = panel.querySelector(".chat-send");
  const messages = panel.querySelector(".chat-messages"), contextText = panel.querySelector("pre");
  const summary = panel.querySelector(".chat-context-summary");
  const recordList = panel.querySelector(".chat-record-list"), sourceList = panel.querySelector(".chat-source-list");
  const draftId = panel.dataset.draftId, revision = Number(panel.dataset.revision);
  const endpoint = `/scopes/${encodeURIComponent(draftId)}/assistant`;
  let ids = [], previous = [], enabled = false, ready = false, busy = false, epoch = 0;
  let activeController = null;
  function report(text, error = false) { status.textContent = text; status.dataset.error = String(error); }
  function buttons() { preview.disabled = !ids.length || busy; send.disabled = !enabled || !ready || busy; }
  function clear() {
    epoch += 1; if (activeController) activeController.abort(); activeController = null;
    previous = []; ready = false; busy = false; messages.replaceChildren(); contextText.textContent = "";
    summary.hidden = true; recordList.replaceChildren(); sourceList.replaceChildren();
    panel.querySelector(".chat-context").open = false;
    form.reset(); buttons();
  }
  function open(value) { body.hidden = !value; toggle.hidden = value; toggle.setAttribute("aria-expanded", String(value)); if (value) { document.dispatchEvent(new CustomEvent("classifire:register-selection-request")); panel.querySelector(".chat-close").focus(); } }
  toggle.addEventListener("click", () => open(true));
  panel.querySelector(".chat-close").addEventListener("click", () => { open(false); toggle.focus(); });
  panel.addEventListener("keydown", (event) => { if (event.key === "Escape") { open(false); toggle.focus(); } });
  panel.querySelector(".chat-clear").addEventListener("click", clear);
  document.addEventListener("classifire:register-selection", (event) => {
    const detail = event.detail || {};
    if (detail.draftId !== draftId || Number(detail.revision) !== revision || !Array.isArray(detail.ids)) { ids = []; clear(); return; }
    const next = [...new Set(detail.ids.filter((id) => typeof id === "string"))].sort();
    if (JSON.stringify(next) === JSON.stringify(ids)) return;
    ids = next; clear();
    panel.querySelector(".chat-selection").textContent = `${ids.length} selected records; saved revision ${revision}. Unsaved edits are not sent.`;
    if (ids.length > 50) { ids = []; report("Select at most 50 records.", true); }
    buttons();
  });
  const errors = {CHAT_UNAVAILABLE:"The assistant is not enabled. You can continue working manually.", CHAT_SELECTION_INVALID:"Selection is not in this saved revision. Save or reopen the register first.", CHAT_CONTEXT_TOO_LARGE:"This context is too large. Select fewer records.", CHAT_CONSENT_REQUIRED:"Confirm sending the previewed context first.", CHAT_PROVIDER_FAILED:"The provider could not return valid advice. No changes were saved.", CHAT_RESPONSE_INVALID:"The provider response could not be verified. No changes were saved.", DRAFT_NOT_FOUND:"This Draft is no longer accessible."};
  async function post(action, question) {
    activeController = new AbortController();
    const response = await fetch(`${endpoint}/${action}`, {method:"POST", credentials:"same-origin", cache:"no-store", signal:activeController.signal, headers:{"Content-Type":"application/json","X-CSRF-Token":panel.dataset.csrf}, body:JSON.stringify({revision, ids, question, previous_questions:previous.slice(-6), consent:form.elements.consent.checked})});
    if (!response.ok) {
      let code = ""; try { code = (await response.json()).detail; } catch (_) { /* Safe fixed fallback. */ }
      throw new Error(errors[code] || "The request was refused. Check your session and selection, then try again.");
    }
    return response.json();
  }
  function showContext(context) {
    const selected = new Set(context.selected_ids);
    const labels = new Map(context.records.map(record => [record.id, record.label || "Observation"]));
    const names = {defects:"Defect", openings:"Opening", services:"Service", observations:"Observation"};
    recordList.replaceChildren(); sourceList.replaceChildren();
    panel.querySelector(".chat-context-basis").textContent = `Saved revision ${context.revision}: ${selected.size} selected record(s), ${context.records.length - selected.size} linked parent record(s).`;
    const order = {defects:0, openings:1, services:2, observations:3};
    [...context.records].sort((left, right) => order[left.kind] - order[right.kind]).forEach(record => {
      const item = document.createElement("li"), heading = document.createElement("strong"), details = document.createElement("span");
      heading.textContent = `${names[record.kind] || "Record"}: ${record.label || "Observation"}${selected.has(record.id) ? "" : " (linked parent)"}`;
      let facts = [];
      if (record.kind === "services") facts = [record.service_type || "Service type unknown", record.quantity === null ? "Quantity unknown" : `Quantity ${record.quantity} ${record.unit}`, record.state];
      if (record.kind === "openings") facts = [record.substrate || "Substrate unknown", record.plane === "unknown" ? "Plane unknown" : record.plane, record.blank ? "Blank opening" : "", `Size ${record.width_mm ?? "unknown"} x ${record.height_mm ?? "unknown"} mm`, record.state];
      if (record.kind === "defects") facts = [record.description || "No saved description"];
      if (record.kind === "observations") facts = [record.text, record.state];
      details.textContent = facts.filter(Boolean).join("; "); item.append(heading, details); recordList.append(item);
    });
    context.source_references.forEach(source => {
      const item = document.createElement("li");
      const kind = {docx:"Word", xlsx:"Excel", pdf:"PDF"}[source.source_kind] || "Source";
      const location = source.row ? `${source.row.sheet}, row ${source.row.row}` : source.page_number ? `page ${source.page_number}` : source.locator || "location not recorded";
      item.textContent = `${kind}: ${location}; ${labels.get(source.record_id) || "selected record"}. ${source.claim_status} (${source.source_id.slice(0,8)}).`;
      sourceList.append(item);
    });
    if (!context.source_references.length) { const item = document.createElement("li"); item.textContent = "No source references for these selected records."; sourceList.append(item); }
    summary.hidden = false;
    contextText.textContent = JSON.stringify(context, null, 2);
    panel.querySelector(".chat-context").open = false;
  }
  preview.addEventListener("click", async () => {
    const version = epoch; busy = true; buttons();
    try { const context = await post("context", "Preview saved context"); if (version !== epoch) return;
      showContext(context); ready = true;
      report(enabled ? "Review this context, then send your question." : "Context is available. The AI provider is not enabled.");
    } catch (error) { if (version === epoch) report(error.message, true); }
    finally { if (version === epoch) { busy = false; buttons(); } }
  });
  function message(label, text) { const item = document.createElement("div"), heading = document.createElement("strong"), content = document.createElement("span"); item.className = "chat-message"; heading.textContent = label; content.textContent = text; item.append(heading, content); messages.append(item); }
  form.addEventListener("submit", async (event) => {
    event.preventDefault(); if (!enabled || !ready || busy || !form.reportValidity()) return;
    const question = form.elements.question.value.trim(); if (!question) return;
    const version = epoch; busy = true; buttons(); report("Waiting for advisory response. Your saved data is unchanged.");
    try { const result = await post("message", question); if (version !== epoch) return;
      message("You", question); message("AI advice - unverified", `${result.answer}\n\nUncertainty: ${result.uncertainty.join("; ")}\nRecord references: ${result.record_ids.join(", ") || "None"}\nSource references: ${result.source_ids.join(", ") || "None"}`);
      previous.push(question); previous = previous.slice(-6); form.elements.question.value = ""; report(result.notice);
    } catch (error) { if (version === epoch) report(error.message, true); }
    finally { if (version === epoch) { busy = false; buttons(); } }
  });
  document.querySelectorAll('form[action="/logout"]').forEach((logout) => logout.addEventListener("submit", clear));
  window.addEventListener("pagehide", clear);
  window.addEventListener("pageshow", (event) => { if (event.persisted) { ids = []; clear(); } });
  fetch(endpoint, {credentials:"same-origin", cache:"no-store"}).then(async (response) => {
    if (!response.ok) throw new Error("Assistant unavailable for this session.");
    const info = await response.json(); enabled = info.enabled === true;
    report(enabled ? `OpenAI / ${info.model}. Preview selected context before sending.` : "AI provider not enabled. Manual work and the external ChatGPT connector remain available."); buttons();
  }).catch(() => report("Assistant unavailable for this session.", true));
})();
