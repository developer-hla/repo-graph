async function fetchMaybe(path, options = {}) {
  try {
    return { ok: true, data: await fetchJson(path, options) };
  } catch (error) {
    return { ok: false, error };
  }
}

async function fetchJson(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "content-type": "application/json",
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(errorMessage(data, response));
  }
  return data;
}

function errorMessage(data, response) {
  if (data && typeof data.detail === "string") return data.detail;
  return `${response.status} ${response.statusText}`.trim();
}
