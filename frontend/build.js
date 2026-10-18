// Bundles src/main.jsx (+ React) into dist/app.js and copies index.html. Usage: node build.js [--watch]
const fs = require("fs");
const path = require("path");
const esbuild = require("esbuild");

const watch = process.argv.includes("--watch");
const dist = path.join(__dirname, "dist");
fs.mkdirSync(dist, { recursive: true });
const copy = () => fs.copyFileSync(path.join(__dirname, "index.html"), path.join(dist, "index.html"));

const options = {
  entryPoints: [path.join(__dirname, "src", "main.jsx")],
  bundle: true,
  minify: !watch,
  sourcemap: watch,
  outfile: path.join(dist, "app.js"),
  loader: { ".js": "jsx", ".jsx": "jsx", ".css": "css" },
  define: { "process.env.NODE_ENV": watch ? '"development"' : '"production"' },
  logLevel: "info",
  target: ["es2019"],
  nodePaths: (process.env.NODE_PATH || "").split(path.delimiter).filter(Boolean),   // lets a global React install work too
};

copy();
if (watch) {
  esbuild.context(options).then((ctx) => ctx.watch()).then(() => console.log("watching for changes... (server.py serves frontend/dist)"));
} else {
  esbuild.build(options).then(() => console.log("built frontend/dist"));
}
