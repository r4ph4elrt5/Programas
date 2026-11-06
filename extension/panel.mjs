import {BridgeError, makeClient, SESSION_KEY, scheduledInstant, TIKTOK_STUDIO, validSession} from "./api.mjs";
import {analyzeSnapshot} from "./snapshot.mjs";

const element = (id) => document.getElementById(id);
const client = makeClient();
let session = null;
let jobs = [];
let selected = null;
let busy = false;

function feedback(message = "", error = false) {
  element("feedback").textContent = message;
  element("feedback").dataset.error = String(error);
}

function connected(value) {
  element("pairing").hidden = value;
  element("workspace").hidden = !value;
  element("connection-state").textContent = value ? "Conectado ao MultiPost" : "Não conectado";
}

async function forget() {
  session = null;
  jobs = [];
  selected = null;
  await chrome.storage.session.remove(SESSION_KEY);
  connected(false);
}

async function run(action) {
  if (busy) return;
  busy = true;
  document.body.setAttribute("aria-busy", "true");
  try {
    await action();
  } catch (error) {
    if (error.status === 401) await forget();
    feedback(error instanceof BridgeError ? error.message : "Não foi possível concluir. Confira o aplicativo e tente novamente.", true);
  } finally {
    busy = false;
    document.body.removeAttribute("aria-busy");
  }
}

function requireSession() {
  if (!validSession(session)) throw new BridgeError("Sessão expirada. Conecte novamente ao MultiPost.", 401);
  return session.token;
}

function displayDate(value) {
  if (!value || !Number.isFinite(Date.parse(value))) return "Sem horário solicitado";
  return new Date(value).toLocaleString("pt-BR", {dateStyle: "short", timeStyle: "short"})
    + ` (${Intl.DateTimeFormat().resolvedOptions().timeZone})`;
}

function localInput(value) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "";
  const pad = (number) => String(number).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

const labels = {
  WAITING_USER: "Pacote pronto · conclua no TikTok", USER_CONFIRMED: "Publicação declarada por você",
  USER_SCHEDULED: "Agendamento declarado por você", READY: "Aguardando preparação",
  SCHEDULED: "Agendado localmente · ainda não agendado no TikTok", CANCELLED: "Tarefa cancelada",
  FAILED: "Preparação falhou", MISSED_SCHEDULE: "Horário local perdido · revise no aplicativo",
};

function renderJob() {
  selected = jobs.find((job) => job.id === element("job-select").value) || null;
  element("job-detail").hidden = !selected;
  element("confirmation").hidden = !selected || !["WAITING_USER", "USER_SCHEDULED"].includes(selected.status);
  element("declared").checked = false;
  element("confirm-result").disabled = true;
  element("result-url").value = "";
  if (!selected) return;
  element("job-title").textContent = selected.title || "Publicação TikTok";
  element("job-state").textContent = labels[selected.status] || selected.status;
  element("video-name").textContent = selected.video_name || "Vídeo preparado";
  element("video-path").value = selected.video_path || "";
  element("caption").value = selected.caption || "";
  element("copy-path").disabled = !selected.video_path;
  element("intended-schedule").textContent = selected.status === "USER_SCHEDULED" && selected.browser_confirmation
    ? "Agendamento declarado por você: " + displayDate(selected.browser_confirmation)
    : selected.scheduled_at
      ? "Horário solicitado no MultiPost: " + displayDate(selected.scheduled_at)
      : "Sem horário solicitado. Escolha Publicar ou Programar no próprio TikTok.";
  element("scheduled-at").value = selected.scheduled_at ? localInput(selected.scheduled_at) : "";
  const scheduledOption = element("outcome").querySelector('option[value="scheduled"]');
  scheduledOption.disabled = selected.status === "USER_SCHEDULED";
  element("outcome").value = selected.status === "USER_SCHEDULED" ? "published"
    : selected.scheduled_at ? "scheduled" : "published";
  element("schedule-fields").hidden = element("outcome").value !== "scheduled";
}

async function refresh() {
  const previous = selected?.id;
  const received = await client.jobs(requireSession());
  // Treat all server fields as data; never turn a caption/title into HTML.
  jobs = received.filter((job) => job && typeof job.id === "string" && typeof job.status === "string");
  const select = element("job-select");
  select.replaceChildren();
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Selecione uma tarefa…";
  select.append(placeholder);
  for (const job of jobs) {
    const option = document.createElement("option");
    option.value = job.id;
    option.textContent = `${job.title || "Vídeo"} · ${labels[job.status] || job.status}`;
    select.append(option);
  }
  select.value = jobs.some((job) => job.id === previous) ? previous : (jobs[0]?.id || "");
  element("empty").hidden = jobs.length > 0;
  renderJob();
}

element("pair-form").addEventListener("submit", (event) => {
  event.preventDefault();
  run(async () => {
    const code = element("pair-code").value.trim();
    session = await client.pair(code);
    await chrome.storage.session.set({[SESSION_KEY]: session});
    element("pair-code").value = "";
    connected(true);
    feedback("Pareamento concluído. A extensão acessa apenas suas tarefas TikTok locais.");
    await refresh();
  });
});
element("refresh").addEventListener("click", () => run(async () => {
  await refresh();
  feedback("Tarefas atualizadas.");
}));
element("job-select").addEventListener("change", renderJob);
element("copy-caption").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(element("caption").value);
    feedback("Legenda copiada. Cole-a no TikTok Studio e confira o texto.");
  } catch { feedback("Não foi possível copiar. Selecione a legenda e use Ctrl+C.", true); }
});
element("copy-path").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(element("video-path").value);
    feedback("Caminho copiado. Cole no campo Nome do seletor de arquivos do TikTok.");
  } catch { feedback("Não foi possível copiar. Selecione o caminho e use Ctrl+C.", true); }
});
element("open-studio").addEventListener("click", () => chrome.tabs.create({url: TIKTOK_STUDIO}));
element("outcome").addEventListener("change", () => {
  element("schedule-fields").hidden = element("outcome").value !== "scheduled";
  element("declared").checked = false;
  element("confirm-result").disabled = true;
});
element("declared").addEventListener("change", () => {
  element("confirm-result").disabled = !element("declared").checked;
});
element("confirm-result").addEventListener("click", () => run(async () => {
  if (!selected || !["WAITING_USER", "USER_SCHEDULED"].includes(selected.status)
      || !element("declared").checked) {
    throw new BridgeError("Selecione uma tarefa preparada e confira a conclusão no TikTok.");
  }
  const outcome = element("outcome").value;
  if (selected.status === "USER_SCHEDULED" && outcome !== "published") {
    throw new BridgeError("Esta tarefa já foi declarada agendada. Registre a publicação somente depois de conferi-la no TikTok.");
  }
  const scheduledAt = outcome === "scheduled" ? scheduledInstant(element("scheduled-at").value) : null;
  const url = element("result-url").value.trim();
  if (url) {
    let parsed;
    try { parsed = new URL(url); } catch { throw new BridgeError("Informe um link HTTPS válido do TikTok."); }
    if (parsed.protocol !== "https:" || !(parsed.hostname === "tiktok.com" || parsed.hostname.endsWith(".tiktok.com"))) {
      throw new BridgeError("Informe um link HTTPS do TikTok, sem links de outras plataformas.");
    }
  }
  const description = outcome === "scheduled"
    ? `Você conferiu no TikTok o agendamento para ${displayDate(scheduledAt)}?`
    : "Você conferiu no TikTok que o vídeo foi publicado?";
  if (!window.confirm(description + "\n\nO MultiPost registrará sua declaração, não uma confirmação da API.")) return;
  await client.confirm(requireSession(), selected.id, {outcome, url, scheduled_at: scheduledAt});
  await refresh();
  feedback(outcome === "scheduled" ? "Agendamento registrado como declaração sua." : "Publicação registrada como declaração sua.");
}));
element("disconnect").addEventListener("click", () => run(async () => {
  try {
    if (validSession(session)) await client.disconnect(session.token);
  } finally {
    await forget();
  }
  feedback("Extensão desconectada. Para revogar qualquer sessão, desative a ponte no MultiPost.");
}));
element("analyze-snapshot").addEventListener("click", () => {
  element("snapshot-result").textContent = "";
  const html = element("snapshot").value;
  if (html.length > 500_000) {
    element("snapshot-result").textContent = "Trecho muito grande. Cole somente o cartão de status, até 500 KB.";
    return;
  }
  try {
    const result = analyzeSnapshot(html);
    element("snapshot-result").textContent = `${result.message || "Análise concluída."} Publicação e agendamento não confirmados.`;
  } catch {
    element("snapshot-result").textContent = "Não foi possível analisar este trecho. Cole um cartão de status válido. Nenhuma publicação ou agendamento foi confirmado.";
  }
});
element("local-timezone").textContent = "Fuso deste computador: " + Intl.DateTimeFormat().resolvedOptions().timeZone;

run(async () => {
  const saved = (await chrome.storage.session.get(SESSION_KEY))[SESSION_KEY];
  if (!validSession(saved)) {
    await forget();
    return;
  }
  session = saved;
  connected(true);
  await refresh();
});
