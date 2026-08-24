const packRoot = () => new URL("static-export/", document.baseURI).href;

const packUrl = (doc, ...segments) =>
  new URL([encodeURIComponent(doc), ...segments.map(encodeURIComponent)].join("/"), packRoot()).href;

/** Base URL of one pack's directory, with the trailing slash relative URLs need. */
const packDocRoot = (doc) => new URL(`${encodeURIComponent(doc)}/`, packRoot()).href;

async function getJson(url) {
  const response = await fetch(url, {cache:"no-store"});
  if (!response.ok) throw new Error(`${response.status} ${url}`);
  const type = response.headers.get("content-type") || "";
  if (!type.includes("json")) throw new Error(`Expected JSON at ${url} but got ${type || "unknown type"}`);
  return response.json();
}

export async function loadIndex() {
  return getJson(new URL("index.json", packRoot()).href);
}

export async function loadManifest(doc) {
  return getJson(packUrl(doc, "manifest.json"));
}

export async function loadTree(doc, file) {
  const relative = String(file || "").replace(/^\/+/, "").split("/")
    .map(encodeURIComponent).join("/");
  return getJson(new URL(relative, packDocRoot(doc)).href);
}

/** Resolve a manifest tree entry's data files (JSON, optional CSV) to download entries. */
export function treeDownloads(doc, treeMeta) {
  const root = packDocRoot(doc);
  const entry = (relative, format) => {
    if (!relative) return null;
    const path = String(relative).replace(/^\/+/, "");
    const name = path.split("/").pop();
    return {
      format,
      name,
      href: new URL(path.split("/").map(encodeURIComponent).join("/"), root).href,
      treeId: treeMeta.id,
      treeLabel: treeMeta.label,
    };
  };
  return [entry(treeMeta?.file, "JSON"), entry(treeMeta?.csv, "CSV")].filter(Boolean);
}

export function pdfHref(manifest) {
  if (manifest?.pdf?.href) {
    return new URL(String(manifest.pdf.href).replace(/^\/+/, ""), packDocRoot(manifest.doc)).href;
  }
  return manifest?.pdf?.remote || null;
}
