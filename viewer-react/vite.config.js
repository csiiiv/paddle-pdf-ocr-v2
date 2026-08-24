import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
import react from "@vitejs/plugin-react";
import {defineConfig} from "vite";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PROJECT = path.resolve(HERE, "..");
const MIME = {".json":"application/json; charset=utf-8", ".pdf":"application/pdf"};

function buildFlagIndex(run) {
  const pagesDir = path.join(PROJECT, "output", run, "002.20-table-structure", "pages");
  if (!fs.existsSync(pagesDir)) return [];
  return fs.readdirSync(pagesDir).filter((name)=>/^page-\d+\.json$/.test(name)).sort().flatMap((name)=>{
    try {
      const payload = JSON.parse(fs.readFileSync(path.join(pagesDir, name), "utf8"));
      const n = Number(payload?.diagnostics?.n_flags ?? payload?.flagged_objects?.length ?? 0);
      const page = Number(payload?.page ?? name.match(/page-(\d+)/)?.[1]);
      return Number.isInteger(page) && n > 0 ? [{page, n_flags:n}] : [];
    } catch { return []; }
  });
}

function repositoryData() {
  const handler = (req, res, next) => {
    const url = new URL(req.url || "/", "http://localhost");
    if (url.pathname === "/api/runs") {
      const root = path.join(PROJECT, "output");
      const runs = fs.existsSync(root) ? fs.readdirSync(root, {withFileTypes:true})
        .filter((entry)=>entry.isDirectory() && fs.existsSync(path.join(root, entry.name, "viewer.json")))
        .map((entry)=>entry.name).sort() : [];
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      res.end(JSON.stringify(runs)); return;
    }
    if (url.pathname === "/api/flag-index") {
      const run = url.searchParams.get("run") || "";
      const safe = run && !run.includes("/") && !run.includes("..");
      const pages = safe ? buildFlagIndex(run) : [];
      const total = pages.reduce((sum, item)=>sum + item.n_flags, 0);
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      res.end(JSON.stringify({run, n_flags:total, n_flagged_pages:pages.length, pages})); return;
    }
    const match = req.url?.split("?")[0].match(/^\/(output|pdfs|fixtures)\/(.+)$/);
    if (!match) return next();
    const root = path.join(PROJECT, match[1]);
    const target = path.resolve(root, decodeURIComponent(match[2]));
    if (!target.startsWith(`${root}${path.sep}`) || !fs.existsSync(target) || !fs.statSync(target).isFile()) return next();
    const size = fs.statSync(target).size;
    const range = req.headers.range?.match(/bytes=(\d*)-(\d*)/);
    res.setHeader("Accept-Ranges", "bytes");
    res.setHeader("Content-Type", MIME[path.extname(target)] || "application/octet-stream");
    if (range) {
      const start = range[1] ? Number(range[1]) : 0;
      const end = range[2] ? Math.min(Number(range[2]), size - 1) : size - 1;
      res.statusCode = 206; res.setHeader("Content-Range", `bytes ${start}-${end}/${size}`); res.setHeader("Content-Length", end-start+1);
      fs.createReadStream(target, {start,end}).pipe(res);
    } else { res.setHeader("Content-Length", size); fs.createReadStream(target).pipe(res); }
  };
  return {name:"repository-data", configureServer(server){server.middlewares.use(handler);}, configurePreviewServer(server){server.middlewares.use(handler);}};
}

export default defineConfig({
  plugins: [react(), repositoryData()],
  base: "./",
  server: {host:"127.0.0.1", port:5173},
  preview: {host:"127.0.0.1", port:4173},
  build: {outDir:"dist", emptyOutDir:true},
  test: {environment:"jsdom", setupFiles:"./src/test-setup.js"},
});
