// All calls to the FastAPI backend live here, so pages stay simple.
export const BASE = "http://127.0.0.1:8000";

async function request(path, options) {
  let res;
  try {
    res = await fetch(BASE + path, options);
  } catch {
    throw new Error("Cannot reach the backend. Is uvicorn running on port 8000?");
  }

  let data = null;
  try {
    data = await res.json();
  } catch {
    /* response had no JSON body */
  }

  if (!res.ok) {
    const detail = data && data.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
        ? detail.map((d) => d.msg).join(", ")
        : `Request failed (${res.status})`;
    throw new Error(message);
  }
  return data;
}

export function uploadDocument(file) {
  const form = new FormData();
  form.append("file", file);
  return request("/documents/upload", { method: "POST", body: form });
}

export function listDocuments(status) {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return request(`/documents${query}`);
}

export const getDocument = (id) => request(`/documents/${id}`);
export const getAudit = (id) => request(`/documents/${id}/audit`);
export const revalidate = (id) => request(`/documents/${id}/validate`, { method: "POST" });

export function decide(id, { action, reviewer, comment }) {
  return request(`/documents/${id}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, reviewer, comment }),
  });
}
