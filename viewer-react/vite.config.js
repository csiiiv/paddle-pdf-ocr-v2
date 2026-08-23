import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
import react from "@vitejs/plugin-react";
import {defineConfig} from "vite";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PROJECT = path.resolve(HERE, "..");
const MIME = {".json":"application/json; charset=utf-8", ".pdf":"application/pdf"};

function repositoryData() {
  const handler = (req, res, next) => {
    if (req.url?.split("?")[0] === "/api/runs") {
      const root = path.join(PROJECT, "output");
      const runs = fs.existsSync(root) ? fs.readdirSync(root, {withFileTypes:true})
        .filter((entry)=>entry.isDirectory() && fs.existsSync(path.join(root, entry.name, "viewer.json")))
        .map((entry)=>entry.name).sort() : [];
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      res.end(JSON.stringify(runs)); return;
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
