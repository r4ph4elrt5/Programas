export const BASE_URL = "http://127.0.0.1:8765";
export const SESSION_KEY = "multipost_companion_session";
export const TIKTOK_STUDIO = "https://www.tiktok.com/tiktokstudio/upload";

export class BridgeError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.name = "BridgeError";
    this.status = status;
  }
}

export function validSession(value, timestamp = Date.now()) {
  return Boolean(value && typeof value.token === "string" && /^[A-Za-z0-9_-]{32,256}$/.test(value.token)
    && typeof value.expires_at === "string" && Date.parse(value.expires_at) > timestamp);
}

export function scheduledInstant(value, timestamp = Date.now()) {
  const parsed = new Date(value);
  if (!value || !Number.isFinite(parsed.getTime()) || parsed.getTime() <= timestamp) {
    throw new BridgeError("Escolha uma data e hora futuras no fuso deste computador.");
  }
  return parsed.toISOString();
}

export function makeClient(fetcher = globalThis.fetch, extensionId = globalThis.chrome?.runtime?.id) {
  if (!/^[a-p]{32}$/.test(extensionId || "")) {
    throw new BridgeError("Abra o assistente pela extensão instalada no navegador.");
  }
  async function request(path, {token, body} = {}) {
    // Callers cannot replace the loopback origin, follow a redirect or forward cookies.
    if (!/^\/companion\/[a-z0-9/_-]+$/i.test(path)) {
      throw new BridgeError("Operação local inválida.");
    }
    const headers = {Accept: "application/json", "X-MultiPost-Extension": extensionId};
    if (token) headers.Authorization = `Bearer ${token}`;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    let response;
    try {
      response = await fetcher(BASE_URL + path, {
        method: body === undefined ? "GET" : "POST", headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        credentials: "omit", redirect: "error", cache: "no-store", referrerPolicy: "no-referrer",
        signal: AbortSignal.timeout(10000),
      });
    } catch {
      throw new BridgeError("Não foi possível acessar o MultiPost. Ative a ponte no aplicativo e tente novamente.");
    }
    if (!response.ok) {
      if (response.status === 401) throw new BridgeError("Pareamento expirado ou revogado. Conecte novamente.", 401);
      if (response.status === 429) throw new BridgeError("Muitas tentativas. Gere um novo código no MultiPost.", 429);
      if (response.status === 400 || response.status === 409 || response.status === 422) {
        throw new BridgeError("A tarefa ou os dados não permitem esta operação. Atualize e confira o horário e o link.", response.status);
      }
      throw new BridgeError("A ponte não concluiu a operação. Confira o aplicativo e tente novamente.", response.status);
    }
    try {
      return await response.json();
    } catch {
      throw new BridgeError("Resposta inesperada da ponte local.");
    }
  }
  return {
    async pair(code) {
      if (!/^\d{8}$/.test(code)) throw new BridgeError("Digite os oito números mostrados no MultiPost.");
      const session = await request("/companion/pair", {body: {code}});
      if (!validSession(session)) throw new BridgeError("O pareamento local não retornou uma sessão válida.");
      return {token: session.token, expires_at: session.expires_at};
    },
    async jobs(token) {
      const result = await request("/companion/jobs", {token});
      if (!Array.isArray(result.jobs) || result.mode !== "ASSISTED_PUBLISH") {
        throw new BridgeError("A ponte não retornou tarefas assistidas válidas.");
      }
      return result.jobs;
    },
    confirm(token, identity, body) {
      if (!/^[a-z0-9_-]{1,128}$/i.test(identity)) throw new BridgeError("Identificador de tarefa inválido.");
      return request(`/companion/jobs/${identity}/confirm`, {token, body});
    },
    disconnect(token) {
      return request("/companion/disconnect", {token, body: {}});
    },
  };
}
