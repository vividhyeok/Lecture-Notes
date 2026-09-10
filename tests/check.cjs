const fs = require("node:fs"),
  cp = require("node:child_process"),
  path = require("node:path");
for (const file of fs.readdirSync("extension").filter((f) => f.endsWith(".js")))
  cp.execFileSync(process.execPath, ["--check", path.join("extension", file)], {
    stdio: "inherit",
  });
const manifest = JSON.parse(
  fs.readFileSync("extension/manifest.json", "utf8").replace(/^\uFEFF/, ""),
);
if (
  manifest.manifest_version !== 3 ||
  manifest.host_permissions.includes("<all_urls>")
)
  throw Error("manifest regression");
for (const file of [
  manifest.background.service_worker,
  manifest.side_panel.default_path,
  ...manifest.content_scripts.flatMap((c) => c.js),
  "config.bootstrap.js",
])
  if (!fs.existsSync(path.join("extension", file)))
    throw Error("missing " + file);
const html = fs.readFileSync("extension/panel.html", "utf8");
for (const match of html.matchAll(/(?:src|href)="([^"]+\.(?:js|css))"/g))
  if (match[1] !== "config.local.js" && !fs.existsSync(path.join("extension", match[1])))
    throw Error("missing asset " + match[1]);
const worker = fs.readFileSync("extension/worker.js", "utf8");
if (
  !worker.includes('importScripts("config.bootstrap.js", "context-router.js")') ||
  !worker.includes('importScripts("config.local.js")') ||
  !/try\s*\{[\s\S]*importScripts\("config\.local\.js"\)[\s\S]*\}\s*catch/.test(worker)
)
  throw Error("service worker must tolerate a missing per-PC config.local.js");

const pkg = JSON.parse(fs.readFileSync("package.json", "utf8"));
const lock = JSON.parse(fs.readFileSync("package-lock.json", "utf8"));
if (
  pkg.version !== manifest.version ||
  lock.version !== manifest.version ||
  lock.packages?.[""]?.version !== manifest.version
)
  throw Error("release version metadata is out of sync");

const app = fs.readFileSync("backend/app.py", "utf8");
if (!app.includes("manifest.json") || !app.includes("['version']"))
  throw Error("server health version must come from the extension manifest");
const start = fs.readFileSync("start.ps1", "utf8");
if (
  !start.includes("$ExpectedVersion") ||
  !start.includes("$health.version") ||
  !start.includes("Get-NetTCPConnection -LocalPort 18765")
)
  throw Error("START must replace a stale Lecture Notes server by version");
const update = fs.readFileSync("update.ps1", "utf8");
if (
  !update.includes("Get-NetTCPConnection -LocalPort 18765") ||
  !update.includes("Lecture Notes v$($manifest.version) is running from this folder")
)
  throw Error("UPDATE must replace a server started from another installation folder");

console.log("Extension syntax, manifest, assets and update guards passed");
require('./navigation.cjs');
require('./context-router.cjs');
