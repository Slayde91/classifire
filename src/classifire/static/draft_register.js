/* A view over the existing Draft payload. Saving remains the shared revision form. */
"use strict";
(() => {
  const host = document.getElementById("scope-register");
  const bridge = window.classifireScopeEditor;
  if (!host || !bridge) return;
  const form = document.getElementById("scope-editor");
  const writable = form.dataset.canEdit === "true";
  const evidenceStates = ["Unresolved", "Provisional", "Inferred", "Confirmed"];
  const columns = [
    {key:"defect_id",title:"Defect ID",width:155,frozen:true},
    {key:"opening_id",title:"Opening ID",width:155,frozen:true},
    {key:"service_id",title:"Service ID",width:155,frozen:true},
    {key:"defect_label",title:"Defect label",kind:"defect",field:"label",limit:200,required:true},
    {key:"opening_label",title:"Opening label",kind:"opening",field:"label",limit:200,required:true},
    {key:"service_label",title:"Service label",kind:"service",field:"label",limit:200,required:true},
    {key:"service_type",title:"Service type",kind:"service",field:"service_type",limit:500},
    {key:"substrate",title:"Substrate",kind:"opening",field:"substrate",limit:500},
    {key:"plane",title:"Plane",kind:"opening",field:"plane",choices:["unknown","wall","floor","soffit"]},
    {key:"width_mm",title:"Width mm",kind:"opening",field:"width_mm",decimal:true},
    {key:"height_mm",title:"Height mm",kind:"opening",field:"height_mm",decimal:true},
    {key:"quantity",title:"Quantity",kind:"service",field:"quantity",decimal:true},
    {key:"unit",title:"Unit",kind:"service",field:"unit",choices:["each","m","mm"]},
    {key:"service_state",title:"Service evidence",kind:"service",field:"state",choices:evidenceStates},
    {key:"opening_state",title:"Opening evidence",kind:"opening",field:"state",choices:evidenceStates},
    {key:"defect_description",title:"Defect description",kind:"defect",field:"description",limit:4000,width:300},
    {key:"system",title:"Proposed Technical System",width:240},
    {key:"price",title:"Price",width:170},
    {key:"status",title:"Review / source status",width:320},
  ];
  let context = {targets:{},evidence_refs:[]};
  try { context = JSON.parse(document.getElementById("scope-register-context")?.textContent || "{}"); } catch { /* Fail closed to no selected result. */ }
  let payload = bridge.read(), rows = [], anchor = [0,0], end = [0,0];
  let sort = null, undo = [], redo = [], ownChange = false, dragging = false, editor = null;
  let modified = document.getElementById("scope-download").hidden;
  const node = (tag, text, cls) => { const value = document.createElement(tag); if (text !== undefined) value.textContent = text; if (cls) value.className = cls; return value; };
  const button = (label, action) => { const b=node("button",label,"button button-secondary button-small"); b.type="button"; b.addEventListener("click",action); return b; };
  host.append(node("h2","Defect register"));
  const guide=node("ul",undefined,"register-guide");
  ["Select cells, row numbers or column headings. Drag or use Shift to extend a range.","Double-click or press Enter to edit. Paste a rectangular range, fill or clear permitted fields; save one new revision when ready.","Identifiers and relationships stay protected here. Unknowns and historical relationships remain visible for review."].forEach(t=>guide.append(node("li",t)));
  host.append(guide);
  const toolbar=node("div",undefined,"register-toolbar");
  const search=node("input"); search.type="search"; search.placeholder="Search all records"; search.setAttribute("aria-label","Search defect register");
  const filter=node("select"); filter.setAttribute("aria-label","Filter register rows");
  [["working","Linked working records"],["all","All records"],["review","Relationship review queue"],["service","Services"],["blank","Blank openings"],["unresolved","Unresolved relationships"]].forEach(([v,t])=>filter.append(new Option(t,v)));
  const fill=node("input"); fill.type="text"; fill.placeholder="Value for selected cells"; fill.setAttribute("aria-label","Bulk edit value");
  const undoButton=button("Undo",()=>history(false)), redoButton=button("Redo",()=>history(true));
  toolbar.append(search,filter,fill,button("Fill selection",()=>applyFill(fill.value)),button("Clear selection",()=>applyFill("")),undoButton,redoButton);
  const arrange=node("select"); arrange.setAttribute("aria-label","Column to move");
  columns.filter(c=>!c.frozen).forEach(c=>arrange.append(new Option(c.title,c.key)));
  toolbar.append(arrange,button("Move column left",()=>moveColumn(-1)),button("Move column right",()=>moveColumn(1)));
  host.append(toolbar);
  const status=node("p","", "register-status"); status.setAttribute("role","status"); status.setAttribute("aria-live","polite"); host.append(status);
  const error=node("p","","alert alert-error"); error.hidden=true; error.setAttribute("role","alert"); host.append(error);
  const viewport=node("div",undefined,"register-viewport");
  const table=node("table",undefined,"register-grid"); table.setAttribute("role","grid"); table.setAttribute("aria-label","Editable defect register"); table.setAttribute("aria-multiselectable","true");
  viewport.append(table); host.append(viewport);
  const showError = message => { error.textContent=message; error.hidden=false; };
  const clone = value => JSON.parse(JSON.stringify(value));
  const bounds = () => [Math.min(anchor[0],end[0]),Math.max(anchor[0],end[0]),Math.min(anchor[1],end[1]),Math.max(anchor[1],end[1])];
  function rowValue(row,col) {
    if (col.field) return row[col.kind]?.[col.field] ?? "";
    if (col.key === "service_id" && !row.service && row.opening?.blank) return "No service (blank)";
    if (col.key.endsWith("_id")) return row[col.key.slice(0,-3)]?.id || "Unresolved";
    if (col.key === "status") return row.status;
    if (col.key === "system") return row.target.system_text || "Not selected";
    if (col.key === "price") return row.target.price_text || "Not priced";
    return "";
  }
  function buildRows() {
    const defects=new Map(payload.defects.map(d=>[d.id,d])), openings=new Map(payload.openings.map(o=>[o.id,o]));
    const linked=new Set(); const all=[];
    const add=(opening,service,defect=null)=>{
      defect=opening ? defects.get(opening.defect_id) : defect;
      const issues=[];
      if (service && !opening) issues.push("Opening unresolved");
      if (opening && !defect) issues.push("Defect unresolved");
      if (service && service.opening_ids.length > 1) issues.push("Historical multiple openings; one shared service record");
      if (opening?.blank) issues.push("Blank opening; no service");
      if (opening && !opening.blank && !service) issues.push("Service unresolved");
      if (opening && (!opening.substrate || opening.plane === "unknown")) issues.push("Substrate / plane unresolved");
      if (service && service.quantity === null) issues.push("Quantity unknown");
      if (service && service.state !== "Confirmed") issues.push(service.state + " service");
      if (opening && opening.state !== "Confirmed") issues.push(opening.state + " opening");
      const targetKey=service ? `service:${service.id}` : opening?.blank ? `blank_opening:${opening.id}` : "";
      const rowKey=service && opening ? `opening:${opening.id}:service:${service.id}` : targetKey;
      const target={...(context.targets?.[targetKey] || {}),...(context.row_targets?.[rowKey] || {})};
      if (target.system_opening_id !== opening?.id) {
        Object.keys(target).filter(key=>key.startsWith("system_") || key === "status").forEach(key=>delete target[key]);
      }
      if (target.status) issues.push(String(target.status));
      if (target.system_status) issues.push(`System: ${target.system_status}`);
      if (target.price_status) issues.push(`Price: ${target.price_status}`);
      [target.system_warnings, target.price_warnings].forEach(warnings => {
        if (Array.isArray(warnings)) warnings.forEach(warning => issues.push(typeof warning === "string" ? warning : warning.message || warning.code || "Saved result needs review"));
      });
      const ids=[defect?.id,opening?.id,service?.id].filter(Boolean);
      const refs=(context.evidence_refs || []).filter(ref=>ids.includes(ref.target_id));
      [...new Set(refs.map(ref=>ref.status).filter(value=>typeof value === "string" && value))].forEach(value=>issues.push(`Source: ${value}`));
      issues.push(refs.length ? `${refs.length} retained source references; ${modified ? "edited draft needs recheck" : "review source details"}` : "No entity source reference");
      if (modified && (target.system_text || target.price_text)) issues.push("Saved result; draft has unsaved changes");
      all.push({opening,service,defect,target,status:issues.join("; "),needsReview:(!opening && !!service)||(!!opening && !defect)||(!!service && service.opening_ids.length !== 1)||(!service && !opening)||(!!opening && !opening.blank && !service),unresolved:(!opening && !!service)||(!!opening && !defect)});
    };
    payload.services.forEach(service=>{
      if (!service.opening_ids.length) add(null,service);
      service.opening_ids.forEach(id=>{linked.add(id);add(openings.get(id),service);});
    });
    payload.openings.filter(o=>!linked.has(o.id)).forEach(o=>add(o,null));
    payload.defects.filter(d=>!payload.openings.some(o=>o.defect_id===d.id)).forEach(d=>add(null,null,d));
    const reviewCount=all.filter(row=>row.needsReview).length;
    filter.querySelector('option[value="review"]').textContent=`Relationship review queue (${reviewCount})`;
    const term=search.value.toLocaleLowerCase();
    rows=all.filter(row=>(filter.value!=="working"||!row.needsReview)&&(filter.value!=="review"||row.needsReview)&&(filter.value!=="service"||row.service)&&(filter.value!=="blank"||row.opening?.blank)&&(filter.value!=="unresolved"||row.unresolved)&&(!term||columns.some(c=>String(rowValue(row,c)).toLocaleLowerCase().includes(term))));
    if(sort) rows.sort((a,b)=>String(rowValue(a,sort.col)).localeCompare(String(rowValue(b,sort.col)),undefined,{numeric:true})*sort.direction);
  }
  function selected(focus=false) {
    const [r0,r1,c0,c1]=bounds();
    table.querySelectorAll("td[data-r]").forEach(td=>{
      const r=Number(td.dataset.r),c=Number(td.dataset.c); const yes=r>=r0&&r<=r1&&c>=c0&&c<=c1;
      td.setAttribute("aria-selected",String(yes)); td.tabIndex=r===end[0]&&c===end[1]?0:-1;
    });
    status.textContent=rows.length ? `${rows.length} visible rows. ${r1-r0+1} row(s) by ${c1-c0+1} column(s) selected. Copy: Ctrl/Cmd+C. Paste: Ctrl/Cmd+V. Undo: Ctrl/Cmd+Z.` : "No matching records. Add records in Detailed records, relationships and notes.";
    undoButton.disabled=!writable||!undo.length; redoButton.disabled=!writable||!redo.length;
    if(focus) table.querySelector(`td[data-r="${end[0]}"][data-c="${end[1]}"]`)?.focus();
    const targets=rows.slice(r0,r1+1).map(r=>({defect_id:r.defect?.id||null,opening_id:r.opening?.id||null,service_id:r.service?.id||null}));
    const ids=[...new Set(targets.flatMap(target=>Object.values(target)).filter(Boolean))];
    host.dispatchEvent(new CustomEvent("classifire:register-selection",{bubbles:true,detail:{ids,draftId:form.dataset.draftId || location.pathname.split("/")[2],revision:Number(form.querySelector("[name=expected_revision]").value)}}));
  }
  function select(r,c,extend=false,focus=false) {
    r=Math.max(0,Math.min(rows.length-1,r));c=Math.max(0,Math.min(columns.length-1,c));
    if(!extend) anchor=[r,c]; end=[r,c]; selected(focus);
  }
  function render() {
    editor=null; buildRows(); table.replaceChildren();
    const cg=node("colgroup");cg.append(node("col")); columns.forEach(c=>{const col=node("col");col.style.width=`${c.width||170}px`;cg.append(col);}); table.append(cg);
    const thead=node("thead"),tr=node("tr"),corner=node("th"); corner.append(button("All",()=>{anchor=[0,0];end=[Math.max(0,rows.length-1),columns.length-1];selected();})); tr.append(corner);
    let left=48;
    columns.forEach((col,c)=>{
      const th=node("th");th.scope="col";th.setAttribute("aria-colindex",String(c+2));
      if(col.frozen){th.className="register-frozen";th.style.left=`${left}px`;left+=col.width;}
      const label=button(col.title,e=>{if(e.shiftKey){anchor[0]=0;end=[Math.max(0,rows.length-1),c];}else{anchor=[0,c];end=[Math.max(0,rows.length-1),c];}selected();});label.className="register-heading";
      const sorter=button(sort?.col===col?(sort.direction===1?"↑":"↓"):"↕",()=>{sort={col,direction:sort?.col===col?-sort.direction:1};anchor=[0,0];end=[0,0];render();});sorter.className="register-sort";sorter.setAttribute("aria-label",`Sort ${col.title}`);
      th.setAttribute("aria-sort",sort?.col===col?(sort.direction===1?"ascending":"descending"):"none");th.append(label,sorter);
      const grip=node("span","","register-resize");grip.title=`Resize ${col.title}`;
      grip.addEventListener("pointerdown",e=>{e.preventDefault();e.stopPropagation();const x=e.clientX,w=col.width||170;
        const move=ev=>{col.width=Math.max(100,Math.min(600,w+ev.clientX-x));cg.children[c+1].style.width=`${col.width}px`;};
        const up=()=>{document.removeEventListener("pointermove",move);document.removeEventListener("pointerup",up);render();};document.addEventListener("pointermove",move);document.addEventListener("pointerup",up);});th.append(grip);tr.append(th);
    });thead.append(tr);table.append(thead);
    const body=node("tbody");rows.forEach((row,r)=>{
      const tr=node("tr");tr.setAttribute("aria-rowindex",String(r+2));const label=node("th");label.scope="row";
      label.append(button(String(r+1),e=>{if(!e.shiftKey)anchor=[r,0];else anchor[1]=0;end=[r,columns.length-1];selected();}));tr.append(label);let left=48;
      columns.forEach((col,c)=>{const td=node("td");
        const raw=String(rowValue(row,col));
        const identity=col.frozen ? row[col.key.slice(0,-3)] : null;
        const display=identity?.label || raw;
        const reviewURL=col.key === "system" ? row.target.system_url : col.key === "price" ? row.target.price_url : null;
        const workbench=document.getElementById("register-workbench");
        const capability=col.key === "system" ? "system" : col.key === "price" ? "price" : col.key === "status" ? "evidence" : null;
        if (capability && workbench) {
          const action=button(capability === "evidence" ? "View sources" : display || (capability === "system" ? "Review systems" : "Set price"),()=>{
            select(r,c);
            document.dispatchEvent(new CustomEvent("classifire:register-author",{detail:{
              capability, savedURL:reviewURL, modified, row:{defect_id:row.defect?.id,
              opening_id:row.opening?.id, service_id:row.service?.id, blank:row.opening?.blank,
              label:row.service?.label || row.opening?.label || row.defect?.label, needsReview:row.needsReview,
              systemURL:row.target.system_url, priceURL:row.target.price_url}
            }}));
          });
          action.dataset.registerDefect=row.defect?.id || "";
          action.dataset.registerOpening=row.opening?.id || "";
          action.dataset.registerService=row.service?.id || "";
          action.dataset.registerCapability=capability;
          action.disabled=(capability === "evidence" ? !(row.defect || row.opening || row.service) : (row.needsReview || !(row.service || row.opening?.blank))) || workbench.dataset[capability] !== "true";
          action.title=capability === "evidence" ? action.disabled ? "Select a saved Defect, Opening or Service row." : "Inspect saved source evidence beside this row; no data is changed" : action.disabled ? "Resolve this row's relationships and check access before authoring." : `Work with ${capability === "system" ? "technical candidates" : "prices"} beside this row`;
          if(capability === "evidence")td.append(node("span",display,"register-evidence-status"));
          td.append(action);
        } else if (typeof reviewURL === "string" && reviewURL.startsWith("/scopes/") && !reviewURL.includes("\\")) {
          const link=node("a",display);link.href=reviewURL;link.title=`Review saved ${col.key} result`;td.append(link);
        } else td.textContent=display;
        td.dataset.r=String(r);td.dataset.c=String(c);td.setAttribute("role","gridcell");td.setAttribute("aria-colindex",String(c+2));td.setAttribute("aria-label",`${col.title}: ${display}. ${identity ? "Stable identifier: " + raw : ""}`);td.title=identity ? `${display} - ${raw}. Copy this cell to copy the full stable identifier.` : (raw || "Unknown");
        if(!col.field||!row[col.kind]){td.classList.add("register-protected");td.setAttribute("aria-readonly","true");}
        if(col.frozen){td.classList.add("register-frozen");td.style.left=`${left}px`;left+=col.width;}
        td.addEventListener("pointerdown",e=>{if(editor||e.button!==0||e.target.closest("a,button"))return;e.preventDefault();dragging=true;select(r,c,e.shiftKey,true);});
        td.addEventListener("pointerenter",()=>{if(dragging&&!editor)select(r,c,true);});
        td.addEventListener("dblclick",()=>edit(r,c));tr.append(td);
      });body.append(tr);
    });table.append(body);table.setAttribute("aria-rowcount",String(rows.length+1));table.setAttribute("aria-colcount",String(columns.length+1));
    if(end[0]>=rows.length){anchor=[0,0];end=[0,0];}selected();
  }
  function parseValue(col,value) {
    value=String(value).trim();
    if(col.decimal){if(value==="")return null;if(!/^(0|[1-9][0-9]{0,8})(\.[0-9]{1,6})?$/.test(value))throw new Error(`${col.title}: enter a non-negative decimal with up to 9 whole digits and 6 decimal places, or leave unknown.`);return value;}
    if(col.choices&&!col.choices.includes(value))throw new Error(`${col.title}: choose ${col.choices.join(", ")}.`);
    if(col.required&&!value)throw new Error(`${col.title} cannot be cleared.`);
    if(col.limit&&value.length>col.limit)throw new Error(`${col.title} exceeds ${col.limit} characters.`);
    return value;
  }
  function validate(next) {
    const ids=new Set();["defects","openings","services","observations"].forEach(k=>{if(next[k].length>500)throw new Error("Too many records.");next[k].forEach(i=>{if(ids.has(i.id))throw new Error("Duplicate protected identifier.");ids.add(i.id);if(k!=="observations"&&(!i.label.trim()||i.label.length>200))throw new Error("Every record needs a label (maximum 200 characters).");});});
    const defects=new Set(next.defects.map(d=>d.id)), openings=new Map(next.openings.map(o=>[o.id,o]));
    next.openings.forEach(o=>{if(o.defect_id!==null&&!defects.has(o.defect_id))throw new Error("Opening references an unavailable defect.");});
    next.services.forEach(s=>{if(new Set(s.opening_ids).size!==s.opening_ids.length)throw new Error("Duplicate opening relationship.");s.opening_ids.forEach(id=>{if(!openings.has(id))throw new Error("Service references an unavailable opening.");if(openings.get(id).blank)throw new Error("A blank opening cannot have a service.");});});
    columns.filter(c=>c.field).forEach(c=>next[{defect:"defects",opening:"openings",service:"services"}[c.kind]].forEach(i=>parseValue(c,i[c.field]??"")));
    if(new TextEncoder().encode(JSON.stringify(next)).length>256*1024)throw new Error("The Draft exceeds its existing size limit.");
  }
  function commit(changes) {
    if(!writable)throw new Error("Editing requires project write permission.");
    const next=clone(payload), seen=new Map();
    changes.forEach(([r,c,value])=>{
      const row=rows[r],col=columns[c];if(!row||!col)throw new Error("Paste exceeds the visible register. No changes applied.");
      const entity=row[col.kind];if(!col.field||!entity)throw new Error(`${col.title} is protected or unavailable for this row. Select editable fields only.`);
      const parsed=parseValue(col,value),key=`${entity.id}:${col.field}`;
      if(seen.has(key)&&seen.get(key)!==parsed)throw new Error("Conflicting values target the same shared record. No changes applied.");seen.set(key,parsed);
      const collection={defect:"defects",opening:"openings",service:"services"}[col.kind];next[collection].find(i=>i.id===entity.id)[col.field]=parsed;
    });validate(next);if(JSON.stringify(next)===JSON.stringify(payload))return;
    undo.push(clone(payload));if(undo.length>50)undo.shift();redo=[];replace(next);error.hidden=true;
  }
  function replace(next){ownChange=true;modified=true;payload=clone(next);bridge.replace(next);render();queueMicrotask(()=>{ownChange=false;});}
  function history(forward){if(!writable)return;const source=forward?redo:undo,dest=forward?undo:redo;if(!source.length)return;dest.push(clone(payload));replace(source.pop());}
  function applyFill(value){try{const [r0,r1,c0,c1]=bounds(),changes=[];for(let r=r0;r<=r1;r++)for(let c=c0;c<=c1;c++)changes.push([r,c,value]);commit(changes);}catch(e){showError(e.message);}}
  function tabNext(r,c,backwards) {
    const index=r*columns.length+c+(backwards?-1:1);
    if(index<0||index>=rows.length*columns.length)return false;
    select(Math.floor(index/columns.length),index%columns.length,false,true);return true;
  }
  function focusOutside(backwards) {
    const controls=[...document.querySelectorAll('a[href],button,input,select,textarea,summary,[tabindex]')].filter(el=>!table.contains(el)&&!el.matches(':disabled')&&el.tabIndex>=0&&el.getClientRects().length);
    const ordered=backwards?controls.reverse():controls;
    ordered.find(el=>table.compareDocumentPosition(el)&(backwards?2:4))?.focus();
  }
  function edit(r,c,initial) {
    const col=columns[c],row=rows[r];
    if(initial===undefined && ["system","price","status"].includes(col.key)) { table.querySelector(`td[data-r="${r}"][data-c="${c}"] button`)?.click();return; }
    if(!writable||!col.field||!row?.[col.kind]){showError("This cell is protected. Use the existing review actions for systems, prices and relationships.");return;}
    const td=table.querySelector(`td[data-r="${r}"][data-c="${c}"]`);select(r,c);const input=node(col.choices?"select":"input");
    if(col.choices)col.choices.forEach(v=>input.append(new Option(v,v)));else input.type="text";
    input.value=initial===undefined?rowValue(row,col):initial;input.setAttribute("aria-label",`Edit ${col.title}`);editor=input;td.replaceChildren(input);input.focus();if(input.select)input.select();let done=false;
    const finish=cancel=>{if(done)return;done=true;editor=null;if(!cancel){try{commit([[r,c,input.value]]);}catch(e){showError(e.message);}}render();select(r,c,false,true);};
    input.addEventListener("keydown",e=>{if(["Enter","Escape","Tab"].includes(e.key)){e.preventDefault();e.stopPropagation();finish(e.key==="Escape");if(e.key==="Tab"&&!tabNext(r,c,e.shiftKey))focusOutside(e.shiftKey);}});input.addEventListener("blur",()=>finish(false));
  }
  function moveColumn(direction){const index=columns.findIndex(c=>c.key===arrange.value),target=index+direction;if(index<3||target<3||target>=columns.length)return;[columns[index],columns[target]]=[columns[target],columns[index]];anchor=[0,0];end=[0,0];render();}
  function parseTSV(text){
    if(text.length>256*1024)throw new Error("Clipboard exceeds the Draft size limit.");
    const result=[],row=[];let value="",quoted=false,closed=false;
    for(let i=0;i<text.length;i++){const ch=text[i];if(quoted){if(ch==='"'){if(text[i+1]==='"'){value+='"';i++;}else{quoted=false;closed=true;}}else value+=ch;continue;}
      if(ch==='"'&&!value&&!closed){quoted=true;continue;}
      if(ch==='\t'||ch==='\n'||ch==='\r'){row.push(value);value="";closed=false;if(ch!=='\t'){if(ch==='\r'&&text[i+1]==='\n')i++;result.push(row.splice(0));}continue;}
      if(closed)throw new Error("Malformed quoted clipboard value.");value+=ch;
    }if(quoted)throw new Error("Unclosed quoted clipboard value.");if(value||row.length||!result.length){row.push(value);result.push(row);}if(result.some(r=>r.length!==result[0].length))throw new Error("Paste a rectangular selection with equal column counts.");return result;
  }
  table.addEventListener("copy",e=>{if(editor||!rows.length)return;const [r0,r1,c0,c1]=bounds();const lines=[];for(let r=r0;r<=r1;r++){const cells=[];for(let c=c0;c<=c1;c++){let v=String(rowValue(rows[r],columns[c]));if(/[\t\r\n"]/.test(v))v='"'+v.replaceAll('"','""')+'"';cells.push(v);}lines.push(cells.join("\t"));}e.clipboardData.setData("text/plain",lines.join("\r\n"));e.preventDefault();});
  table.addEventListener("paste",e=>{if(editor)return;e.preventDefault();try{const matrix=parseTSV(e.clipboardData.getData("text/plain")),[r0,r1,c0,c1]=bounds();if(matrix.length===1&&matrix[0].length===1){applyFill(matrix[0][0]);return;}if((r0!==r1||c0!==c1)&&(matrix.length!==r1-r0+1||matrix[0].length!==c1-c0+1))throw new Error("Clipboard dimensions must match the selected range.");const changes=[];matrix.forEach((values,r)=>values.forEach((v,c)=>changes.push([r0+r,c0+c,v])));commit(changes);}catch(err){showError(err.message);}});
  table.addEventListener("focusin",event=>{
    const cell=event.target.closest("td[data-r]");
    if(cell && event.target===cell && !editor) {
      const r=Number(cell.dataset.r),c=Number(cell.dataset.c);
      if(r!==end[0] || c!==end[1])select(r,c);
    }
  });
  table.addEventListener("keydown",e=>{if(editor||e.target.closest("a,button,input,select,textarea"))return;const mod=e.ctrlKey||e.metaKey;if(mod&&e.key.toLowerCase()==="z"){e.preventDefault();history(e.shiftKey);return;}if(mod&&e.key.toLowerCase()==="y"){e.preventDefault();history(true);return;}if(mod&&e.key.toLowerCase()==="a"){e.preventDefault();anchor=[0,0];end=[Math.max(0,rows.length-1),columns.length-1];selected();return;}
    if(e.key==="Tab"){if(tabNext(end[0],end[1],e.shiftKey))e.preventDefault();return;}
    const delta={ArrowUp:[-1,0],ArrowDown:[1,0],ArrowLeft:[0,-1],ArrowRight:[0,1]}[e.key];if(delta){e.preventDefault();select(end[0]+delta[0],end[1]+delta[1],e.key!=="Tab"&&e.shiftKey,true);return;}
    if(e.key==="Home"||e.key==="End"){e.preventDefault();select(mod?(e.key==="Home"?0:rows.length-1):end[0],e.key==="Home"?0:columns.length-1,e.shiftKey,true);return;}
    if(e.key==="Enter"||e.key==="F2"){e.preventDefault();edit(...end);return;}if(e.key==="Delete"||e.key==="Backspace"){e.preventDefault();applyFill("");return;}
    if(!mod&&!e.altKey&&e.key.length===1){e.preventDefault();edit(...end,e.key);}
  });
  document.addEventListener("pointerup",()=>{dragging=false;});
  document.addEventListener("classifire:register-selection-request",()=>selected());
  [search,filter].forEach(input=>input.addEventListener("input",()=>{anchor=[0,0];end=[0,0];render();}));
  form.addEventListener("scope:changed",()=>{if(ownChange)return;payload=bridge.read();modified=true;undo=[];redo=[];render();});
  // Opening a closed detail panel makes native validation errors discoverable.
  form.addEventListener("invalid",()=>{const details=form.querySelector(".scope-detail-editor");if(details)details.open=true;},true);
  if(!writable)toolbar.querySelectorAll("button,input:not([type=search])").forEach(el=>{el.disabled=true;});
  document.addEventListener("classifire:register-results",event=>{
    if (!event.detail || typeof event.detail.targets !== "object") return;
    context=event.detail;render();
  });
  document.querySelector("[data-clear-review-selection]")?.addEventListener("click",()=>{
    document.querySelectorAll('.register-artifacts [name="match"] option').forEach(option=>{option.selected=false;});
  });
  render();
})();
