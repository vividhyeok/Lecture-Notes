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
])
  if (!fs.existsSync(path.join("extension", file)))
    throw Error("missing " + file);
const html = fs.readFileSync("extension/panel.html", "utf8");
for (const match of html.matchAll(/(?:src|href)="([^"]+\.(?:js|css))"/g))
  if (!fs.existsSync(path.join("extension", match[1])))
    throw Error("missing asset");
console.log("Extension syntax, manifest and assets passed");
require('./navigation.cjs');
require('./context-router.cjs');
