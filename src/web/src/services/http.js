import { API_BASE } from "../config/api";

export async function requestJson(
  path,
  { method = "GET", body, token, onUnauthorized, headers = {} } = {}
) {
  const requestHeaders = { ...headers };

  if (!(body instanceof FormData)) {
    requestHeaders["Content-Type"] = "application/json";
  }

  if (token) {
    requestHeaders.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: requestHeaders,
    body:
      body === undefined
        ? undefined
        : body instanceof FormData
        ? body
        : JSON.stringify(body),
  });

  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (response.status === 401 && onUnauthorized) {
    onUnauthorized();
  }

  if (!response.ok) {
    const message = data?.detail || `Request failed with status ${response.status}`;
    throw new Error(message);
  }

  return data;
}
