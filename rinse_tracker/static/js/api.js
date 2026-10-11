// Thin fetch wrapper. Errors carry the server's message and per-field errors.
export class ApiError extends Error {
  constructor(message, fields = {}, status = 0) {
    super(message);
    this.fields = fields;
    this.status = status;
  }
}

async function request(method, url, body) {
  const opts = { method, headers: {} };
  if (body instanceof FormData) {
    opts.body = body;
  } else if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let resp;
  try {
    resp = await fetch(url, opts);
  } catch {
    throw new ApiError("Can't reach Rinse Tracker. Is the app still running?");
  }
  let data = null;
  try { data = await resp.json(); } catch { /* non-JSON response */ }
  if (!resp.ok) {
    throw new ApiError((data && data.error) || `Request failed (${resp.status}).`,
      (data && data.fields) || {}, resp.status);
  }
  return data;
}

export const api = {
  get: (url) => request("GET", url),
  post: (url, body) => request("POST", url, body ?? {}),
  put: (url, body) => request("PUT", url, body ?? {}),
  del: (url) => request("DELETE", url),
};

export function qs(params) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== "" && v != null) p.set(k, v);
  const s = p.toString();
  return s ? `?${s}` : "";
}
