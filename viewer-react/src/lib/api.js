const productionPrefix = new URL("../..", window.location.href).pathname.replace(/\/$/, "");
export const dataUrl = (path) => `${import.meta.env.DEV ? "" : productionPrefix}/${path.replace(/^\//, "")}`;

export async function json(path, optional=false) {
  try {
    const response = await fetch(dataUrl(path), {cache:"no-store"});
    if (!response.ok) throw new Error(`${response.status} ${path}`);
    return await response.json();
  } catch (error) { if (optional) return null; throw error; }
}

export async function listRuns() {
  if (import.meta.env.DEV) {
    const response = await fetch("/api/runs", {cache:"no-store"});
    if (response.ok) return response.json();
  }
  const response = await fetch(dataUrl("output/"), {cache:"no-store"});
  if (!response.ok) return [];
  const html = await response.text();
  return [...html.matchAll(/href="([^"?#]+?)\/?"/gi)].map((match)=>decodeURIComponent(match[1]).replace(/\/$/,""))
    .filter((name)=>name && name!==".." && !name.includes("/"));
}

export const runPath = (run, path) => `output/${encodeURIComponent(run)}/${path}`;
export const pagePath = (run, stage, page) => runPath(run, `${stage}/pages/page-${String(page).padStart(4,"0")}.json`);

export function pdfUrls(metadataPath) {
  const filename = String(metadataPath || "").split(/[\\/]/).pop();
  const remote = /^https?:\/\//i.test(String(metadataPath || "")) ? metadataPath : null;
  return [...new Set([dataUrl(`pdfs/${encodeURIComponent(filename)}`), remote].filter(Boolean))];
}
