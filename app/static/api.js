// Client for the FastAPI backend.

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status; // 0 when the server could not be reached
  }
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(path, options);
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError(0, "Serveur injoignable");
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // not JSON: keep the status text
    }
    throw new ApiError(response.status, detail);
  }
  return response;
}

export const getStatus = async () => (await request("/health/ready")).json();

export const getDocuments = async () => (await request("/documents")).json();

export const fileUrl = (source, page) =>
  `/documents/file?source=${encodeURIComponent(source)}${page ? `#page=${page}` : ""}`;

export async function uploadDocument(file, token) {
  const body = new FormData();
  body.append("file", file);
  const response = await request("/documents", {
    method: "POST",
    body,
    headers: { "X-Admin-Token": token },
  });
  return response.json();
}

export async function deleteDocument(source, token) {
  await request(`/documents?source=${encodeURIComponent(source)}`, {
    method: "DELETE",
    headers: { "X-Admin-Token": token },
  });
}

/** POST /chat streams NDJSON events: `sources`, then `token`s, then `done` (or `error`). */
export async function* chat(body, signal) {
  const response = await request("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop();
    for (const line of lines) if (line.trim()) yield JSON.parse(line);
  }
  if (buffer.trim()) yield JSON.parse(buffer);
}
