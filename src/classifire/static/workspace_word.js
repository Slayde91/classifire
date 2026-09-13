"use strict";
(() => {
  const panel = document.getElementById("workspace-chat");
  const section = panel?.querySelector(".chat-attachments");
  const form = section?.querySelector(".chat-word-upload");
  if (!form || !panel.dataset.draftId) return;
  const draft = encodeURIComponent(panel.dataset.draftId), base = `/scopes/${draft}/assistant/word`;
  const list = section.querySelector(".chat-word-sources"), status = section.querySelector(".chat-word-status");
  const destination = section.querySelector(".chat-word-destination");
  let busy = false, loaded = false, canWrite = false, limit = 0, generation = 0;
  const element = (tag, text, className = "") => {
    const node = document.createElement(tag); node.textContent = text; node.className = className; return node;
  };
  function report(text, error = false) { status.textContent = text; status.dataset.error = String(error); }
  function controls() {
    section.querySelectorAll("button").forEach(button => { button.disabled = busy; });
    form.querySelector("button").disabled = busy || !loaded || !canWrite; form.elements.file.disabled = busy || !canWrite;
  }
  const errors = {
    SCOPE_DOCX_UPLOAD_INVALID: "Choose a supported DOCX within the displayed size limit.",
    SCOPE_DOCX_UPLOAD_CONFLICT: "These bytes belong to a different source purpose. Use the existing source workflow.",
    SCOPE_DOCX_SOURCE_LIMIT: "This Draft has reached its retained Word report limit.",
    SCOPE_DOCX_NOT_READY: "This report is not ready for inspection. Review its scan status.",
    SCOPE_DOCX_SOURCE_INTEGRITY_FAILED: "The retained report could not be verified. Refresh its status.",
  };
  async function request(path = "", options = {}) {
    const current = generation;
    let response;
    try { response = await fetch(base + path, {credentials:"same-origin", cache:"no-store", ...options}); }
    catch { throw new Error("Connection interrupted. Refresh retained reports before trying again."); }
    if (current !== generation) throw new Error("Workspace changed. Refresh retained reports.");
    if (!response.ok) {
      let code = ""; try { code = (await response.json()).detail; } catch { /* Fixed safe fallback. */ }
      if ([401, 403, 404].includes(response.status)) { list.replaceChildren(); loaded = false; }
      throw new Error(errors[code] || "Request refused. Check your session, access and report scan status.");
    }
    const data = await response.json();
    if (current !== generation) throw new Error("Workspace changed. Refresh retained reports.");
    return data;
  }
  function button(text, action) {
    const node = element("button", text, "button button-secondary button-small");
    node.type = "button"; node.addEventListener("click", action); return node;
  }
  function sourceCard(source) {
    const card = element("article", "", "chat-word-source");
    card.append(element("h4", source.filename), element("p", `${source.size_bytes} bytes | Scan: ${source.status}`));
    card.append(element("p", `Original SHA256: ${source.sha256}`, "chat-word-hash"));
    if (source.processing_error) card.append(element("p", `Processing could not finish: ${source.processing_error}`));
    const actions = element("div", "", "chat-actions");
    if (canWrite && source.status !== "malware_detected") actions.append(button("Scan and prepare report", () => scan(source.id)));
    if (source.ready) actions.append(button("Inspect retained evidence", () => inspect(source.id, card, 0)));
    const link = element("a", "Open Word review", "button button-secondary button-small");
    link.href = `/scopes/${draft}/word/${encodeURIComponent(source.id)}`;
    actions.append(link); card.append(actions, element("div", "", "chat-word-evidence")); return card;
  }
  async function load() {
    const data = await request();
    if (data.draft_id !== panel.dataset.draftId) throw new Error("Destination changed. Reopen the Draft.");
    limit = data.max_upload_bytes; canWrite = data.can_write === true; form.hidden = !canWrite;
    destination.textContent = `Destination: ${data.reference} - ${data.name}. Maximum ${Math.floor(limit / 1048576)} MB per DOCX.`;
    if (!canWrite) destination.textContent += " Read only: attaching and scanning require write permission.";
    list.replaceChildren(...data.sources.map(sourceCard));
    if (!data.sources.length) list.append(element("p", "No Word reports retained for this Draft."));
    loaded = true;
  }
  async function operation(work, progress, success) {
    if (busy) return;
    const current = generation; busy = true; controls(); report(progress);
    try { await work(); if (current === generation) report(success); }
    catch (error) { if (current === generation) report(error.message || "Result unavailable. Refresh retained reports before trying again.", true); }
    finally { if (current === generation) { busy = false; controls(); } }
  }
  function reload() {
    return operation(load, "Loading retained reports.", "Retained reports refreshed. Scanning and reading require their separate controls.");
  }
  section.querySelector(".chat-word-refresh").addEventListener("click", reload);
  section.addEventListener("toggle", () => { if (section.open && !loaded && !busy) reload(); });
  form.addEventListener("submit", event => {
    event.preventDefault(); if (busy || !loaded || !canWrite || !form.reportValidity()) return;
    const file = form.elements.file.files[0];
    if (!file || !file.name.toLowerCase().endsWith(".docx") || !file.size || file.size > limit) {
      report("Choose a nonempty DOCX within the displayed size limit.", true); return;
    }
    // Capture before disabling controls. Upload is distinct from an AI message.
    const body = new FormData(form);
    operation(async () => { await request("/upload", {method:"POST", body}); form.elements.file.value = ""; await load(); },
      "Retaining this report in CLASSIFIRE. No scan or AI request is running.",
      "Report retained. Choose Scan and prepare report when ready; Scope is unchanged.");
  });
  function scan(sourceId) {
    const body = new URLSearchParams({csrf_token:panel.dataset.csrf});
    operation(async () => { await request(`/${encodeURIComponent(sourceId)}/scan`, {method:"POST", body}); await load(); },
      "Scanning and preparing the selected report. No AI request is running.",
      "Scan attempt finished. Check the report status before inspection; no Scope changes were saved.");
  }
  function inspect(sourceId, card, after) {
    if (busy) return;
    const content = card.querySelector(".chat-word-evidence"); content.replaceChildren();
    operation(async () => {
      const data = await request(`/${encodeURIComponent(sourceId)}?after_block=${after}`);
      content.append(element("p", "Retained evidence only. Structural locations are not Word page numbers; picture placement does not prove service or opening ownership."));
      content.append(element("p", `Document SHA256: ${data.document_sha256}`, "chat-word-hash"));
      const pictures = new Map(data.pictures.map(picture => [picture.id, picture]));
      for (const block of data.blocks) {
        const part = element("div", "", "chat-word-block");
        part.append(element("strong", block.locator), element("pre", block.text));
        for (const id of block.pictures) {
          const picture = pictures.get(id); if (!picture) continue;
          const figure = element("figure", ""), image = document.createElement("img");
          image.alt = `Retained ${picture.id} at ${picture.locator}`;
          image.src = `/scopes/${draft}/word/${encodeURIComponent(sourceId)}/pictures/${encodeURIComponent(id)}`;
          image.addEventListener("error", () => { image.hidden = true; figure.append(element("p", "Picture unavailable. Refresh status and recheck access or scan state.")); });
          figure.append(image, element("figcaption", `${picture.id} | ${picture.locator}`)); part.append(figure);
        }
        content.append(part);
      }
      const navigation = element("div", "", "chat-actions");
      if (after > 0) navigation.append(button("Previous text", () => inspect(sourceId, card, Math.max(0, after - 5))));
      if (data.next_after_block !== null) navigation.append(button("Next text", () => inspect(sourceId, card, data.next_after_block)));
      content.append(navigation);
    }, "Verifying retained evidence and scan state.", "Evidence displayed for inspection. It has not been included in the AI conversation.");
  }
  window.addEventListener("pagehide", () => { generation++; loaded = false; busy = false; list.replaceChildren(); controls(); });
  window.addEventListener("pageshow", event => { if (event.persisted && section.open) reload(); });
  controls();
})();
