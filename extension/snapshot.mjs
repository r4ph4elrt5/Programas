/**
 * Inspect HTML deliberately pasted by the user, entirely offline.
 *
 * This module never reads a TikTok tab, executes pasted scripts, clicks a button,
 * or treats upload completion as publication evidence. A static snapshot cannot
 * establish the current page's state or permission to publish.
 */

function isVisibleInSnapshot(element) {
  for (let node = element; node && node.nodeType === 1; node = node.parentElement) {
    if (node.hasAttribute("hidden") || node.hasAttribute("inert")) return false;
    if (node.getAttribute("aria-hidden")?.toLowerCase() === "true") return false;
    if (node.getAttribute("data-show")?.toLowerCase() === "false") return false;
    const inlineStyle = node.getAttribute("style") || "";
    if (/(?:^|;)\s*display\s*:\s*none\s*(?:!important)?\s*(?:;|$)/i.test(inlineStyle)) return false;
    if (/(?:^|;)\s*visibility\s*:\s*(?:hidden|collapse)\s*(?:!important)?\s*(?:;|$)/i.test(inlineStyle)) return false;
    if (/(?:^|;)\s*content-visibility\s*:\s*hidden\s*(?:!important)?\s*(?:;|$)/i.test(inlineStyle)) return false;
  }
  return true;
}

function visibleMatches(root, selector) {
  return [...root.querySelectorAll(selector)].filter(isVisibleInSnapshot);
}

function uploadState(document) {
  let roots = visibleMatches(document, '[data-e2e="upload_status_container"]');
  if (!roots.length) roots = visibleMatches(document, ".info-body");
  // Several upload widgets may belong to different files. Do not pick a success
  // from an old widget and combine it with the current submit button.
  if (roots.length !== 1) return "unknown";
  const root = roots[0];
  const failed = visibleMatches(root, ".info-status.error, .info-status.failed");
  if (failed.length) return "failed";
  const uploaded = visibleMatches(root, ".info-status.success").some((status) => (
    visibleMatches(status, '[data-icon="CheckCircleFill"], [data-icon="check-circle-fill"]').length > 0
    || /\b(?:enviado|uploaded)\b/i.test(status.textContent || "")
  ));
  const uploading = visibleMatches(root, ".info-status.info").length > 0;
  if (uploaded && uploading) return "unknown";
  if (uploaded) return "uploaded";
  if (uploading) return "uploading";
  // 100%, a successful progress bar, a filename or a Replace button alone
  // provide no evidence that the upload/processing actually completed.
  return "unknown";
}

function checkState(document) {
  const active = visibleMatches(document, '.status-result[data-show="true"]');
  if (!active.length) return "unknown";
  if (active.some((node) => node.classList.contains("status-error")
      || node.classList.contains("status-warn"))) return "blocked";
  if (active.some((node) => node.classList.contains("status-checking")
      || node.classList.contains("status-ready"))) return "pending";
  return active.every((node) => node.classList.contains("status-success")) ? "passed" : "unknown";
}

function submitEnabled(document) {
  const buttons = visibleMatches(document, 'button[data-e2e="post_video_button"]');
  if (buttons.length !== 1) return false;
  const button = buttons[0];
  if (button.hasAttribute("disabled")) return false;
  for (const name of ["aria-disabled", "data-disabled", "data-loading", "aria-busy"]) {
    const value = button.getAttribute(name);
    if (value !== null && value.toLowerCase() !== "false") return false;
  }
  // A disabled fieldset also disables a descendant button, even if the button
  // itself has no disabled attribute.
  if (button.closest("fieldset[disabled]")) return false;
  return true;
}

export function analyzeDocument(document) {
  if (!document || typeof document.querySelectorAll !== "function") {
    throw new TypeError("Forneça um documento HTML para análise local.");
  }
  const upload = uploadState(document);
  const checks = checkState(document);
  const canSubmit = upload === "uploaded" && checks === "passed" && submitEnabled(document);
  let message;
  if (upload === "uploading") message = "O HTML indica upload em andamento. Aguarde no TikTok Studio.";
  else if (upload === "failed") message = "O HTML indica falha de upload. Confira a mensagem no TikTok Studio.";
  else if (checks === "blocked") message = "Há uma verificação com erro ou aviso no HTML. Revise no TikTok Studio.";
  else if (upload === "uploaded" && checks === "pending") {
    message = "O arquivo foi enviado, mas as verificações ainda estão pendentes no HTML.";
  } else if (canSubmit) {
    message = "O HTML indica arquivo enviado, verificações concluídas e botão habilitado. Confira a página atual antes de agir.";
  } else if (upload === "uploaded") {
    message = "O arquivo foi enviado, mas este HTML não permite confirmar que todas as etapas estão prontas.";
  } else message = "Não foi possível identificar o estado do upload neste HTML.";
  return {
    upload, checks, canSubmit, confirmation: "unverified",
    message: `${message} Análise offline: não confirma publicação nem agendamento; estilos externos e o estado atual não são verificados.`,
  };
}

export function analyzeSnapshot(html) {
  if (typeof html !== "string" || !html.trim()) throw new TypeError("Cole um trecho de HTML para analisar.");
  if (html.length > 2_000_000) throw new RangeError("O HTML excede o limite de 2 MB.");
  if (!globalThis.document?.createElement) throw new Error("O analisador requer um documento HTML local.");
  const template = globalThis.document.createElement("template");
  // Template content has an inert owner document: unlike parsing directly into
  // a document with DOMParser, images/frames/styles are not fetched. Nothing in
  // this deliberately supplied markup is ever appended to the extension DOM.
  template.innerHTML = html;
  return analyzeDocument(template.content);
}
