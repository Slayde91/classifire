"use strict";
(() => {
  const panel = document.getElementById("workspace-chat");
  if (!panel) return;
  panel.querySelectorAll(".chat-attachments").forEach(section => {
  const kind = section.dataset.sourceKind || "word", pdf = kind === "pdf", xlsx = kind === "xlsx";
  const format = xlsx ? "XLSX" : pdf ? "PDF" : "DOCX", extension = xlsx ? ".xlsx" : pdf ? ".pdf" : ".docx";
  const form = section?.querySelector(".chat-word-upload");
  if (!form || !panel.dataset.draftId) return;
  const draft = encodeURIComponent(panel.dataset.draftId), base = `/scopes/${draft}/assistant/${kind}`;
  const list = section.querySelector(".chat-word-sources"), status = section.querySelector(".chat-word-status");
  const destination = section.querySelector(".chat-word-destination");
  let busy = false, loaded = false, canWrite = false, limit = 0, generation = 0;
  let selection = null;
  const element = (tag, text, className = "") => {
    const node = document.createElement(tag); node.textContent = text; node.className = className; return node;
  };
  function report(text, error = false) { status.textContent = text; status.dataset.error = String(error); }
  function controls() {
    section.querySelectorAll("button").forEach(button => { button.disabled = busy; });
    section.querySelectorAll("select").forEach(select => {select.disabled=busy;});
    form.querySelector("button").disabled = busy || !loaded || !canWrite; form.elements.file.disabled = busy || !canWrite;
  }
  const errors = {
    SCOPE_XLSX_UPLOAD_INVALID: "Choose a supported XLSX within the displayed size limit.",
    SCOPE_XLSX_UPLOAD_CONFLICT: "These bytes belong to a different source purpose. Use the existing source workflow.",
    SCOPE_XLSX_SOURCE_LIMIT: "This Draft has reached its retained workbook limit.",
    SCOPE_XLSX_NOT_READY: "This workbook is not ready for inspection. Review its scan status.",
    SCOPE_XLSX_SOURCE_INTEGRITY_FAILED: "The retained workbook could not be verified. Refresh its status.",
    PDF_UPLOAD_INVALID: "Choose a supported PDF within the displayed size limit.",
    PDF_UPLOAD_CONFLICT: "These bytes belong to a different source purpose. Use the existing source workflow.",
    PDF_SOURCE_LIMIT: "This Draft has reached its retained PDF report limit.",
    PDF_NOT_READY: "This report is not ready for inspection. Review its scan status.",
    PDF_SOURCE_INTEGRITY_FAILED: "The retained report could not be verified. Refresh its status.",
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
    const link = element("a", xlsx ? "Open Excel mapping review" : pdf ? "Open PDF page review" : "Open Word review", "button button-secondary button-small");
    link.href = `/scopes/${draft}/${xlsx ? "workbooks" : pdf ? "evidence" : "word"}/${encodeURIComponent(source.id)}`;
    if (source.ready) {
      const original=element("a", "Download retained original", "button button-secondary button-small");
      original.href=`${base}/${encodeURIComponent(source.id)}/original`;actions.append(original);
    }
    actions.append(link); card.append(actions, element("div", "", "chat-word-evidence")); return card;
  }
  function publishSelection() {
    if (xlsx) {
      const value=selection?.rows.length ? {...selection,rows:[...selection.rows],picture_ids:[...selection.picture_ids]} : null;
      document.dispatchEvent(new CustomEvent("classifire:xlsx-selection",{detail:{draftId:panel.dataset.draftId,xlsx:value}}));
      section.querySelector(".chat-word-selected").textContent=value ? `Selected worksheet ${value.sheet_index}, header row ${value.header_row}, data rows ${value.rows.join(", ")}; ${value.picture_ids.length} pictures. Preview and consent before sending.` : "Choose at least one data row and its header for AI preview.";
      return;
    }
    if (pdf) {
      const value=selection && (selection.include_text || selection.include_image) ? {...selection} : null;
      document.dispatchEvent(new CustomEvent("classifire:pdf-selection",{detail:{draftId:panel.dataset.draftId,pdf:value}}));
      section.querySelector(".chat-word-selected").textContent=value ? `Selected PDF page ${value.page_number}: text ${value.include_text ? "included" : "excluded"}, image ${value.include_image ? "included" : "excluded"}. Preview and consent before sending.` : "No PDF page selected for AI.";
      return;
    }
    const value = selection && (selection.locators.length || selection.picture_ids.length) ? selection : null;
    document.dispatchEvent(new CustomEvent("classifire:word-selection", {detail:{draftId:panel.dataset.draftId, word:value ? {...value,locators:[...value.locators],picture_ids:[...value.picture_ids]} : null}}));
    section.querySelector(".chat-word-selected").textContent = value
      ? `Selected for preview: ${value.locators.length} text block(s), ${value.picture_ids.length} picture(s). Nothing is sent until preview and consent.`
      : "No report evidence selected for AI.";
  }
  function clearSelection() {
    selection = null; section.querySelectorAll(".chat-word-select").forEach(input => {input.checked=false;}); publishSelection();
  }
  section.querySelector(".chat-word-clear-selection")?.addEventListener("click", clearSelection);
  document.addEventListener("classifire:chat-evidence-clear", clearSelection);
  for(const otherKind of ["word","pdf","xlsx"])if(otherKind!==kind){
    document.addEventListener(`classifire:${otherKind}-selection`,event=>{
      if(event.detail?.draftId===panel.dataset.draftId && event.detail[otherKind])clearSelection();
    });
  }
  function selectControl(data, key, id, label) {
    const wrap=element("label", "", "chat-consent"), input=document.createElement("input");
    input.type="checkbox"; input.className="chat-word-select";
    input.checked=selection?.source_id===data.source_id && selection?.document_sha256===data.document_sha256 && selection[key].includes(id);
    input.addEventListener("change", () => {
      if (!selection || selection.source_id!==data.source_id || selection.document_sha256!==data.document_sha256) {
        section.querySelectorAll(".chat-word-select").forEach(other=>{if(other!==input)other.checked=false;});
        selection={source_id:data.source_id,document_sha256:data.document_sha256,locators:[],picture_ids:[]};
      }
      if (input.checked && selection[key].length >= (key==="locators" ? 10 : 2)) {
        input.checked=false; report("Select at most 10 text blocks and 2 pictures from one report per question.",true); return;
      }
      selection[key]=input.checked ? [...selection[key],id].sort() : selection[key].filter(value=>value!==id);
      publishSelection();
    });
    wrap.append(input,document.createTextNode(label));return wrap;
  }
  async function load() {
    const data = await request();
    if (data.draft_id !== panel.dataset.draftId) throw new Error("Destination changed. Reopen the Draft.");
    limit = data.max_upload_bytes; canWrite = data.can_write === true; form.hidden = !canWrite;
    destination.textContent = `Destination: ${data.reference} - ${data.name}. Maximum ${Math.floor(limit / 1048576)} MB per ${format}.`;
    if (!canWrite) destination.textContent += " Read only: attaching and scanning require write permission.";
    clearSelection();
    list.replaceChildren(...data.sources.map(sourceCard));
    if (!data.sources.length) list.append(element("p", `No ${xlsx ? "Excel" : pdf ? "PDF" : "Word"} reports retained for this Draft.`));
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
    if (!file || !file.name.toLowerCase().endsWith(extension) || !file.size || file.size > limit) {
      report(`Choose a nonempty ${format} within the displayed size limit.`, true); return;
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
    if (xlsx) { inspectXlsx(sourceId, card, 1, 1); return; }
    if (pdf) { inspectPdf(sourceId, card, after || 1); return; }
    const content = card.querySelector(".chat-word-evidence"); content.replaceChildren();
    operation(async () => {
      const data = await request(`/${encodeURIComponent(sourceId)}?after_block=${after}`);
      content.append(element("p", "Retained evidence only. Structural locations are not Word page numbers; picture placement does not prove service or opening ownership."));
      content.append(element("p", `Document SHA256: ${data.document_sha256}`, "chat-word-hash"));
      const pictures = new Map(data.pictures.map(picture => [picture.id, picture]));
      for (const block of data.blocks) {
        const part = element("div", "", "chat-word-block");
        part.append(element("strong", block.locator), element("pre", block.text), selectControl(data,"locators",block.locator,"Include this text in AI preview"));
        for (const id of block.pictures) {
          const picture = pictures.get(id); if (!picture) continue;
          const figure = element("figure", ""), image = document.createElement("img");
          image.alt = `Retained ${picture.id} at ${picture.locator}`;
          image.src = `/scopes/${draft}/word/${encodeURIComponent(sourceId)}/pictures/${encodeURIComponent(id)}`;
          image.addEventListener("error", () => { image.hidden = true; figure.append(element("p", "Picture unavailable. Refresh status and recheck access or scan state.")); });
          figure.append(image, element("figcaption", `${picture.id} | ${picture.locator}`), selectControl(data,"picture_ids",id,"Include this picture in AI preview")); part.append(figure);
        }
        content.append(part);
      }
      const navigation = element("div", "", "chat-actions");
      if (after > 0) navigation.append(button("Previous text", () => inspect(sourceId, card, Math.max(0, after - 5))));
      if (data.next_after_block !== null) navigation.append(button("Next text", () => inspect(sourceId, card, data.next_after_block)));
      content.append(navigation);
    }, "Verifying retained evidence and scan state.", "Evidence displayed for inspection. Select items explicitly before previewing an AI request.");
  }
  function selectXlsxControl(data,key,value,label,header) {
    const wrap=element("label","","chat-consent"),input=document.createElement("input");input.type="checkbox";input.className="chat-word-select";
    const same=()=>selection?.source_id===data.source_id && selection?.document_sha256===data.document_sha256 && selection?.sheet_index===data.sheet.index && selection?.header_row===Number(header.value);
    input.checked=!!(same()&&selection[key].includes(value));
    if(key==="rows"){input.dataset.xlsxRow=String(value);input.disabled=value<=Number(header.value);}
    input.addEventListener("change",()=>{
      const headerRow=Number(header.value);
      if(!Number.isInteger(headerRow)||headerRow<1||headerRow>=data.sheet.rows||(key==="rows"&&value<=headerRow)){input.checked=false;report("Choose a valid header and data rows after it.",true);return;}
      if(!same()){
        section.querySelectorAll(".chat-word-select").forEach(other=>{if(other!==input)other.checked=false;});
        selection={source_id:data.source_id,document_sha256:data.document_sha256,sheet_index:data.sheet.index,header_row:headerRow,rows:[],picture_ids:[]};
      }
      if(input.checked&&selection[key].length>=(key==="rows"?10:2)){input.checked=false;report("Select at most 10 data rows and 2 pictures from one worksheet.",true);return;}
      selection[key]=input.checked?[...selection[key],value].sort((a,b)=>key==="rows"?a-b:String(a).localeCompare(String(b))):selection[key].filter(item=>item!==value);
      publishSelection();
    });wrap.append(input,document.createTextNode(label));return wrap;
  }
  function inspectXlsx(sourceId,card,sheet,row) {
    const content=card.querySelector(".chat-word-evidence");content.replaceChildren();content.classList.add("chat-word-block");
    operation(async()=>{
      const data=await request(`/${encodeURIComponent(sourceId)}?sheet=${sheet}&row=${row}`);
      content.append(element("p",`Sheet ${data.sheet.index}: ${data.sheet.name}. Rows ${data.start_row}-${data.end_row} of ${data.sheet.rows}. Inspection only; no AI request, mapping or Scope save.`));
      content.append(element("p",`Document SHA256: ${data.document_sha256}`,"chat-word-hash"));
      const label=element("label","Worksheet"),choose=document.createElement("select");choose.className="chat-xlsx-sheet";
      for(const item of data.sheets){const option=element("option",`${item.index}: ${item.name}`);option.value=item.index;option.selected=item.index===sheet;choose.append(option);}
      choose.addEventListener("change",()=>{if(!busy)inspectXlsx(sourceId,card,Number(choose.value),1);});label.append(choose);content.append(label);
      const headerLabel=element("label","Header row (included in AI preview with selected data rows)"),header=document.createElement("input");header.type="number";header.min="1";header.max=String(Math.max(1,data.sheet.rows-1));header.className="chat-xlsx-header";
      header.value=String(selection?.source_id===data.source_id&&selection?.sheet_index===sheet?selection.header_row:1);
      header.addEventListener("change",()=>{clearSelection();content.querySelectorAll("[data-xlsx-row]").forEach(input=>{input.disabled=Number(input.dataset.xlsxRow)<=Number(header.value);});report("Header changed. Choose data rows, preview and consent again.");});headerLabel.append(header);content.append(headerLabel);
      content.append(element("p","Cell values retain their parser type. Formulas are source text, never evaluated; cached values are not quantities. Empty cells and missing relationships remain unknown."));
      for(let current=data.start_row;current<=data.end_row;current++){
        const block=element("div","","chat-word-block");block.append(element("h5",`Row ${current}`),selectXlsxControl(data,"rows",current,"Include this data row and header in AI preview",header));
        const cells=data.cells.filter(cell=>cell.row===current);
        for(const cell of cells)block.append(element("strong",`${cell.address} (${cell.kind})`),element("pre",cell.value));
        if(!cells.length)block.append(element("p","No retained nonempty cells in this row."));content.append(block);
      }
      content.append(element("p",`${data.images.length} picture anchor(s) intersect these rows; ${data.omitted_images} other picture(s) omitted. Anchors show worksheet placement, not defect or service ownership.`));
      for(const picture of data.images){
        const figure=element("figure",""),image=document.createElement("img");image.alt=`Retained ${picture.occurrence_id} from ${data.sheet.name}`;
        image.src=`/scopes/${draft}/workbooks/${encodeURIComponent(sourceId)}/images/${sheet}/${encodeURIComponent(picture.occurrence_id)}.png`;
        image.addEventListener("error",()=>{image.hidden=true;figure.append(element("p","Picture unavailable. Recheck access and scan status."));});
        figure.append(image,element("figcaption",`${picture.occurrence_id}; anchor ${JSON.stringify(picture.anchor)}; original SHA256 ${picture.sha256}; preview SHA256 ${picture.preview_sha256}.`),selectXlsxControl(data,"picture_ids",picture.occurrence_id,"Include this picture in AI preview",header));content.append(figure);
      }
      const navigation=element("div","","chat-actions");
      if(row>1)navigation.append(button("Previous rows",()=>inspectXlsx(sourceId,card,sheet,Math.max(1,row-5))));
      if(data.next_row)navigation.append(button("Next rows",()=>inspectXlsx(sourceId,card,sheet,data.next_row)));
      const review=element("a","Review this worksheet","button button-secondary button-small");review.href=`/scopes/${draft}/workbooks/${encodeURIComponent(sourceId)}?sheet=${sheet}&row=${row}`;navigation.append(review);content.append(navigation);
    },"Verifying retained worksheet evidence and scan state.","Worksheet displayed. Select rows/header and pictures, then preview and consent. Mapping and Scope confirmation remain separate.");
  }
  function selectPdfControl(data,key,label) {
    const wrap=element("label","","chat-consent"),input=document.createElement("input");
    input.type="checkbox";input.className="chat-word-select";
    const same=()=>selection?.source_id===data.source_id && selection?.document_sha256===data.document_sha256 && selection?.page_number===data.page.page_number;
    input.checked=!!(same()&&selection[key]);
    input.addEventListener("change",()=>{
      if(!same()){
        section.querySelectorAll(".chat-word-select").forEach(other=>{if(other!==input)other.checked=false;});
        selection={source_id:data.source_id,document_sha256:data.document_sha256,page_number:data.page.page_number,include_text:false,include_image:false};
      }
      selection[key]=input.checked;publishSelection();
    });
    wrap.append(input,document.createTextNode(label));return wrap;
  }
  function inspectPdf(sourceId, card, page) {
    const content=card.querySelector(".chat-word-evidence");content.replaceChildren();content.classList.add("chat-word-block");
    operation(async () => {
      const data=await request(`/${encodeURIComponent(sourceId)}?page=${page}`);
      content.append(element("p", `Page ${data.page.page_number} of ${data.total_pages}. Retained evidence only; no model request or Scope save.`));
      content.append(element("p", `Document SHA256: ${data.document_sha256}`, "chat-word-hash"));
      content.append(element("strong", data.page.locator_key), element("pre", data.page.text), selectPdfControl(data,"include_text","Include this page text in AI preview"));
      const image=document.createElement("img");image.alt=`Retained PDF page ${page}`;
      image.src=`/scopes/${draft}/evidence/${encodeURIComponent(sourceId)}/pages/${page}.png`;
      image.addEventListener("error",()=>{image.hidden=true;content.append(element("p","Page image unavailable. Recheck access and current scan status."));});
      content.append(image,selectPdfControl(data,"include_image","Include this page image in AI preview"));
      const navigation=element("div", "", "chat-actions");
      if(page>1)navigation.append(button("Previous page",()=>inspectPdf(sourceId,card,page-1)));
      if(page<data.total_pages)navigation.append(button("Next page",()=>inspectPdf(sourceId,card,page+1)));
      const review=element("a", "Review this PDF page", "button button-secondary button-small");
      review.href=`/scopes/${draft}/evidence/${encodeURIComponent(sourceId)}?page=${page}`;
      navigation.append(review);content.append(navigation);
    }, "Verifying the selected PDF page and scan state.", "PDF page displayed. Select text/image explicitly, then preview and consent. Scope confirmation remains separate.");
  }
  window.addEventListener("pagehide", () => { generation++; loaded = false; busy = false; clearSelection(); list.replaceChildren(); controls(); });
  window.addEventListener("pageshow", event => { if (event.persisted && section.open) reload(); });
  controls();
  });
})();
