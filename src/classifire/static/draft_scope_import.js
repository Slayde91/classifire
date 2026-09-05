"use strict";

(() => {
  const form = document.getElementById("scope-import-upload");
  if (!form) return;
  const picker = document.getElementById("scope-import-file");
  const artifact = document.getElementById("scope-import-artifact");
  const button = document.getElementById("scope-import-preview-button");
  const status = document.getElementById("scope-import-file-status");
  const error = document.getElementById("scope-import-client-error");
  const confirmControls = document.getElementById("scope-import-confirm-controls");
  const maxBytes = 294912;
  let reader = null;

  function fail(message) {
    artifact.value = "";
    button.disabled = true;
    error.textContent = message;
    error.hidden = false;
    status.textContent = "Choose a valid file to continue.";
  }

  picker.addEventListener("change", () => {
    if (reader && reader.readyState === FileReader.LOADING) reader.abort();
    artifact.value = "";
    button.disabled = true;
    error.hidden = true;
    if (confirmControls) confirmControls.disabled = true;
    const file = picker.files[0];
    if (!file) {
      status.textContent = "Choose a file to continue.";
      return;
    }
    if (!file.size || file.size > maxBytes) {
      fail("Choose a nonempty Draft Scope JSON file no larger than 288 KiB (294,912 bytes).");
      return;
    }
    status.textContent = "Reading the selected file for preview. Nothing is saved.";
    const selectedReader = new FileReader();
    reader = selectedReader;
    selectedReader.addEventListener("load", () => {
      if (picker.files[0] !== file || reader !== selectedReader) return;
      const result = selectedReader.result;
      if (typeof result !== "string" || !result.includes(";base64,")) {
        fail("The file could not be read safely. Select it again.");
        return;
      }
      artifact.value = result.slice(result.indexOf(",") + 1);
      button.disabled = false;
      status.textContent = `${file.name} is ready to preview (${file.size.toLocaleString()} bytes). Nothing is saved.`;
    });
    selectedReader.addEventListener("error", () => {
      if (reader === selectedReader) fail("The file could not be read. Select it again.");
    });
    try { selectedReader.readAsDataURL(file); }
    catch { fail("The file could not be read. Select it again."); }
  });

  form.addEventListener("submit", (event) => {
    if (!artifact.value || button.disabled) {
      event.preventDefault();
      fail("Wait for the selected file to finish loading, then preview it.");
    }
  });
})();
