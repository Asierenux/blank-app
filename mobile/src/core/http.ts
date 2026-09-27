import { StoreError } from './types';

const USER_AGENT =
  'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36';
const TIMEOUT_MS = 15000;

type Params = Record<string, string | number>;

export function withParams(url: string, params?: Params): string {
  if (!params) return url;
  const qs = Object.entries(params)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join('&');
  return `${url}${url.includes('?') ? '&' : '?'}${qs}`;
}

async function request(
  store: string,
  url: string,
  init: RequestInit & { params?: Params } = {},
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  const { params, headers, ...rest } = init;
  try {
    const resp = await fetch(withParams(url, params), {
      ...rest,
      headers: {
        'User-Agent': USER_AGENT,
        'Accept-Language': 'es-ES,es;q=0.9',
        Accept: 'application/json',
        ...(headers as Record<string, string>),
      },
      signal: controller.signal,
    });
    if (!resp.ok) throw new StoreError(`${store}: HTTP ${resp.status}`);
    return resp;
  } catch (err) {
    if (err instanceof StoreError) throw err;
    const reason = (err as Error)?.name === 'AbortError' ? 'tiempo de espera agotado' : String(err);
    throw new StoreError(`${store}: ${reason}`);
  } finally {
    clearTimeout(timer);
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function getJson(store: string, url: string, init?: RequestInit & { params?: Params }): Promise<any> {
  const resp = await request(store, url, init);
  try {
    return await resp.json();
  } catch {
    throw new StoreError(`${store}: respuesta no válida (¿ha cambiado la web?)`);
  }
}

export async function getHtml(store: string, url: string, init?: RequestInit & { params?: Params }) {
  const resp = await request(store, url, {
    ...init,
    headers: { Accept: 'text/html,application/xhtml+xml', ...(init?.headers as Record<string, string>) },
  });
  return resp.text();
}
