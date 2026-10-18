async function call(path, body) {
  const res = await fetch(path, body === undefined ? undefined : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const text = await res.text();
  let json = null;
  try { json = JSON.parse(text); } catch (e) { /* not json */ }
  if (!res.ok) throw new Error((json && json.error) || `Request failed (${res.status})`);
  return json;
}

export const api = {
  config: () => call("/api/config"),
  analyze: (body) => call("/api/analyze", body),
  whatif: (scenario) => call("/api/whatif", { scenario }),
  signature: () => call("/api/signature"),
};
