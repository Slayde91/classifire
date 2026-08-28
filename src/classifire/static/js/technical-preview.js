(() => {
  "use strict";

  const host = document.querySelector("[data-technical-pdf-preview]");
  if (!host) {
    return;
  }

  const previousButton = host.querySelector("[data-preview-previous]");
  const nextButton = host.querySelector("[data-preview-next]");
  const loadButton = host.querySelector("[data-preview-load]");
  const fitButton = host.querySelector("[data-preview-fit]");
  const actualButton = host.querySelector("[data-preview-actual]");
  const pageInput = host.querySelector("[data-preview-page]");
  const pageCountLabel = host.querySelector("[data-preview-page-count]");
  const status = host.querySelector("[data-preview-status]");
  const stage = host.querySelector(".technical-preview-stage");
  const image = host.querySelector("[data-preview-image]");
  const sourceSha256 = host.dataset.sourceSha256 || "";
  const sourceSizeRaw = host.dataset.sourceSize || "";
  const sourceSize = Number.parseInt(sourceSizeRaw, 10);
  const urlPrefix = host.dataset.previewUrlPrefix || "";
  const configuredMaximum = Number.parseInt(host.dataset.maxPages || "", 10);
  const maximumPngBytes = 25 * 1024 * 1024;
  const maximumEdgePixels = 4096;
  const maximumPixels = 8_000_000;
  const requestTimeoutMilliseconds = 20_000;
  const verifiedPageEvent = "classifire:technical-preview-page-verified";

  const initializationFailure = () => {
    host.setAttribute("aria-busy", "false");
    let target = status;
    if (!target) {
      target = document.createElement("p");
      target.className = "alert alert-error";
      target.setAttribute("role", "alert");
      host.append(target);
    }
    target.textContent = (
      "The controlled page preview could not start. Use the original-report download."
    );
  };

  if (
    !previousButton
    || !nextButton
    || !loadButton
    || !fitButton
    || !actualButton
    || !pageInput
    || !pageCountLabel
    || !status
    || !stage
    || !image
    || !/^[0-9a-f]{64}$/.test(sourceSha256)
    || !/^[1-9][0-9]*$/.test(sourceSizeRaw)
    || !Number.isSafeInteger(sourceSize)
    || sourceSize > 100 * 1024 * 1024
    || !urlPrefix.startsWith("/")
    || urlPrefix.startsWith("//")
    || !Number.isSafeInteger(configuredMaximum)
    || configuredMaximum < 1
    || configuredMaximum > 500
  ) {
    initializationFailure();
    return;
  }

  let currentPage = 1;
  let pageCount = null;
  let activeController = null;
  let requestSequence = 0;

  const parseBoundedInteger = (value, maximum) => {
    if (typeof value !== "string" || !/^[1-9][0-9]*$/.test(value)) {
      return null;
    }
    const parsed = Number.parseInt(value, 10);
    return Number.isSafeInteger(parsed) && parsed <= maximum ? parsed : null;
  };

  const sha256Hex = async (value) => {
    if (!globalThis.crypto || !globalThis.crypto.subtle) {
      throw new Error("PREVIEW_DIGEST_UNAVAILABLE");
    }
    const digest = await globalThis.crypto.subtle.digest("SHA-256", value);
    return Array.from(new Uint8Array(digest), (byte) => (
      byte.toString(16).padStart(2, "0")
    )).join("");
  };

  const pngDataUrl = (buffer) => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      if (typeof reader.result === "string" && reader.result.startsWith("data:image/png;base64,")) {
        resolve(reader.result);
      } else {
        reject(new Error("PREVIEW_IMAGE_ENCODING_INVALID"));
      }
    });
    reader.addEventListener("error", () => reject(new Error("PREVIEW_IMAGE_ENCODING_INVALID")));
    reader.readAsDataURL(new Blob([buffer], {type: "image/png"}));
  });

  const parsePngDimensions = (buffer) => {
    if (buffer.byteLength < 33) {
      throw new Error("PREVIEW_SIGNATURE_INVALID");
    }
    const bytes = new Uint8Array(buffer);
    if (
      bytes[0] !== 0x89
      || bytes[1] !== 0x50
      || bytes[2] !== 0x4e
      || bytes[3] !== 0x47
      || bytes[4] !== 0x0d
      || bytes[5] !== 0x0a
      || bytes[6] !== 0x1a
      || bytes[7] !== 0x0a
      || bytes[8] !== 0x00
      || bytes[9] !== 0x00
      || bytes[10] !== 0x00
      || bytes[11] !== 0x0d
      || bytes[12] !== 0x49
      || bytes[13] !== 0x48
      || bytes[14] !== 0x44
      || bytes[15] !== 0x52
    ) {
      throw new Error("PREVIEW_SIGNATURE_INVALID");
    }
    const view = new DataView(buffer);
    return {height: view.getUint32(20), width: view.getUint32(16)};
  };

  const messageForStatus = (responseStatus) => {
    if (responseStatus === 401 || responseStatus === 403) {
      return "Your session cannot access this source. Refresh and sign in again.";
    }
    if (responseStatus === 404) {
      return "That physical PDF page is not available.";
    }
    if (responseStatus === 409) {
      return "The retained source no longer matches this page. Refresh before reviewing.";
    }
    if (responseStatus === 413) {
      return "This page exceeds the controlled preview limits. Use the attachment download.";
    }
    if (responseStatus === 415) {
      return "Controlled inline preview currently supports PDF sources only.";
    }
    if (responseStatus === 422) {
      return "This PDF page could not be rendered within the controlled boundary.";
    }
    if (responseStatus === 503 || responseStatus === 504) {
      return "The controlled preview worker is disabled, busy, or unavailable. Try again shortly.";
    }
    return "The source-bound preview could not be confirmed. Use the attachment download.";
  };

  const setControls = (loading) => {
    host.setAttribute("aria-busy", loading ? "true" : "false");
    pageInput.disabled = loading;
    loadButton.disabled = loading;
    previousButton.disabled = loading || currentPage <= 1;
    nextButton.disabled = loading || pageCount === null || currentPage >= pageCount;
    fitButton.disabled = loading || image.hidden;
    actualButton.disabled = loading || image.hidden;
  };

  const clearImage = () => {
    image.hidden = true;
    image.removeAttribute("src");
  };

  const fail = (message) => {
    clearImage();
    status.textContent = message;
    setControls(false);
  };

  const setZoom = (mode) => {
    const fit = mode === "fit";
    image.classList.toggle("technical-preview-image-fit", fit);
    fitButton.setAttribute("aria-pressed", fit ? "true" : "false");
    actualButton.setAttribute("aria-pressed", fit ? "false" : "true");
  };

  const validateReceiptHeaders = (response, requestedPage) => {
    const contentType = (response.headers.get("Content-Type") || "").split(";", 1)[0].trim();
    const cacheControl = (response.headers.get("Cache-Control") || "").toLowerCase();
    const source = response.headers.get("X-Classifire-Source-SHA256");
    const renderedSourceSize = parseBoundedInteger(
      response.headers.get("X-Classifire-Source-Size"),
      100 * 1024 * 1024,
    );
    const renderedPage = parseBoundedInteger(
      response.headers.get("X-Classifire-Preview-Page"),
      configuredMaximum,
    );
    const renderedPageCount = parseBoundedInteger(
      response.headers.get("X-Classifire-Preview-Page-Count"),
      configuredMaximum,
    );
    const width = parseBoundedInteger(
      response.headers.get("X-Classifire-Preview-Width"),
      maximumEdgePixels,
    );
    const height = parseBoundedInteger(
      response.headers.get("X-Classifire-Preview-Height"),
      maximumEdgePixels,
    );
    const contentLength = parseBoundedInteger(
      response.headers.get("Content-Length"),
      maximumPngBytes,
    );
    const pngSha256 = response.headers.get("X-Classifire-Preview-PNG-SHA256") || "";
    const bindingSha256 = response.headers.get(
      "X-Classifire-Preview-Binding-SHA256",
    ) || "";
    const policy = response.headers.get("X-Classifire-Preview-Policy");
    const rendererHeader = response.headers.get("X-Classifire-Preview-Renderer") || "";
    const rendererMatch = /^([A-Za-z0-9][A-Za-z0-9._+-]{0,63})\/([A-Za-z0-9][A-Za-z0-9._+-]{0,63})$/.exec(
      rendererHeader,
    );
    if (
      contentType !== "image/png"
      || !cacheControl.includes("no-store")
      || response.headers.get("X-Content-Type-Options") !== "nosniff"
      || source !== sourceSha256
      || renderedSourceSize !== sourceSize
      || renderedPage !== requestedPage
      || renderedPageCount === null
      || renderedPage > renderedPageCount
      || width === null
      || height === null
      || width * height > maximumPixels
      || contentLength === null
      || !/^[0-9a-f]{64}$/.test(pngSha256)
      || !/^[0-9a-f]{64}$/.test(bindingSha256)
      || policy !== "technical-pdf-preview-v1"
      || !rendererMatch
      || rendererMatch[1] !== "PyMuPDF"
    ) {
      throw new Error("PREVIEW_RECEIPT_INVALID");
    }
    return {
      bindingSha256,
      contentLength,
      height,
      pageCount: renderedPageCount,
      pageNumber: renderedPage,
      pngSha256,
      policy,
      renderer: rendererMatch[1],
      rendererVersion: rendererMatch[2],
      source,
      sourceSize: renderedSourceSize,
      width,
    };
  };

  const bindingDigest = async (receipt) => {
    if (typeof globalThis.TextEncoder !== "function") {
      throw new Error("PREVIEW_DIGEST_UNAVAILABLE");
    }
    const canonical = JSON.stringify({
      height_pixels: receipt.height,
      page_count: receipt.pageCount,
      page_number: receipt.pageNumber,
      png_sha256: receipt.pngSha256,
      policy_version: receipt.policy,
      renderer: receipt.renderer,
      renderer_version: receipt.rendererVersion,
      source_sha256: receipt.source,
      source_size_bytes: receipt.sourceSize,
      width_pixels: receipt.width,
    });
    return sha256Hex(new TextEncoder().encode(canonical));
  };

  const restoreFocus = (initiatingControl) => {
    if (!initiatingControl) {
      return;
    }
    let focusTarget = initiatingControl;
    if (
      !focusTarget
      || !focusTarget.isConnected
      || focusTarget.disabled
      || typeof focusTarget.focus !== "function"
    ) {
      focusTarget = pageInput.disabled ? stage : pageInput;
    }
    if (typeof focusTarget.focus === "function") {
      focusTarget.focus({preventScroll: true});
    }
  };

  const loadPage = async (requestedPage, initiatingControl = null) => {
    if (
      !Number.isSafeInteger(requestedPage)
      || requestedPage < 1
      || requestedPage > configuredMaximum
      || (pageCount !== null && requestedPage > pageCount)
    ) {
      fail("Enter a valid physical PDF page number.");
      restoreFocus(initiatingControl);
      return;
    }
    if (activeController) {
      activeController.abort();
    }
    const sequence = requestSequence + 1;
    requestSequence = sequence;
    const controller = new AbortController();
    activeController = controller;
    const timeout = globalThis.setTimeout(
      () => controller.abort(),
      requestTimeoutMilliseconds,
    );
    status.textContent = `Rendering physical PDF page ${requestedPage} from verified source bytes...`;
    setControls(true);
    try {
      const response = await fetch(`${urlPrefix}${requestedPage}`, {
        cache: "no-store",
        credentials: "same-origin",
        headers: {"Accept": "image/png"},
        redirect: "error",
        signal: controller.signal,
      });
      if (!response.ok) {
        throw Object.assign(new Error("PREVIEW_REQUEST_REJECTED"), {responseStatus: response.status});
      }
      const receipt = validateReceiptHeaders(response, requestedPage);
      const buffer = await response.arrayBuffer();
      if (buffer.byteLength !== receipt.contentLength) {
        throw new Error("PREVIEW_LENGTH_MISMATCH");
      }
      const dimensions = parsePngDimensions(buffer);
      if (
        dimensions.width !== receipt.width
        || dimensions.height !== receipt.height
        || dimensions.width > maximumEdgePixels
        || dimensions.height > maximumEdgePixels
        || dimensions.width * dimensions.height > maximumPixels
      ) {
        throw new Error("PREVIEW_DIMENSIONS_INVALID");
      }
      const actualSha256 = await sha256Hex(buffer);
      if (actualSha256 !== receipt.pngSha256) {
        throw new Error("PREVIEW_DIGEST_MISMATCH");
      }
      const actualBindingSha256 = await bindingDigest(receipt);
      if (actualBindingSha256 !== receipt.bindingSha256) {
        throw new Error("PREVIEW_BINDING_MISMATCH");
      }
      const dataUrl = await pngDataUrl(buffer);
      if (sequence !== requestSequence) {
        return;
      }
      image.src = dataUrl;
      image.alt = `Raster preview of physical PDF page ${requestedPage}`;
      if (typeof image.decode === "function") {
        await image.decode();
      }
      if (sequence !== requestSequence) {
        return;
      }
      currentPage = requestedPage;
      pageCount = receipt.pageCount;
      pageInput.value = String(currentPage);
      pageInput.max = String(pageCount);
      pageCountLabel.textContent = `Page ${currentPage} of ${pageCount}`;
      status.textContent = (
        `Controlled raster preview verified: ${receipt.width} x ${receipt.height} pixels. `
        + "Use the physical PDF page number when recording a source locator."
      );
      image.hidden = false;
      host.dispatchEvent(new CustomEvent(verifiedPageEvent, {
        bubbles: true,
        detail: Object.freeze({
          bindingSha256: receipt.bindingSha256,
          pageCount: receipt.pageCount,
          pageNumber: receipt.pageNumber,
          pngSha256: receipt.pngSha256,
          sourceSha256: receipt.source,
          sourceSize: receipt.sourceSize,
        }),
      }));
    } catch (error) {
      if (sequence !== requestSequence) {
        return;
      }
      if (error && error.name === "AbortError") {
        fail("The controlled preview timed out. Try again or use the attachment download.");
      } else {
        fail(messageForStatus(error && error.responseStatus));
      }
    } finally {
      globalThis.clearTimeout(timeout);
      if (sequence === requestSequence) {
        if (activeController === controller) {
          activeController = null;
        }
        setControls(false);
        restoreFocus(initiatingControl);
      }
    }
  };

  previousButton.addEventListener("click", (event) => (
    loadPage(currentPage - 1, event.currentTarget)
  ));
  nextButton.addEventListener("click", (event) => (
    loadPage(currentPage + 1, event.currentTarget)
  ));
  loadButton.addEventListener("click", (event) => {
    const requested = parseBoundedInteger(pageInput.value.trim(), configuredMaximum);
    if (requested === null) {
      fail("Enter a valid physical PDF page number.");
      restoreFocus(event.currentTarget);
      return;
    }
    loadPage(requested, event.currentTarget);
  });
  pageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      const requested = parseBoundedInteger(pageInput.value.trim(), configuredMaximum);
      if (requested === null) {
        fail("Enter a valid physical PDF page number.");
        restoreFocus(pageInput);
        return;
      }
      loadPage(requested, pageInput);
    }
  });
  fitButton.addEventListener("click", () => setZoom("fit"));
  actualButton.addEventListener("click", () => setZoom("actual"));

  setZoom("fit");
  loadPage(1);
})();
