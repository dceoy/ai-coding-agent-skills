import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";
import { spawnSync } from "node:child_process";

const code = readFileSync(new URL("../../skills/gas-drive-html-server/templates/Code.gs", import.meta.url), "utf8")
  .replace("__ROOT_FOLDER_ID__", "abcdefghijROOT123456789");
function iterator(items) {
  let i = 0;
  return { hasNext: () => i < items.length, next: () => items[i++] };
}
function folder(id, name, parents = []) {
  return { getId: () => id, getName: () => name, getParents: () => iterator(parents),
    getFolders: () => iterator([]), getFiles: () => iterator([]),
    getLastUpdated: () => new Date("2026-10-14"), getSize: () => 0 };
}
function file(id, name, parents, mime = "text/html") {
  return { getId: () => id, getName: () => name, getParents: () => iterator(parents),
    getMimeType: () => mime, getSize: () => 50,
    getLastUpdated: () => new Date("2026-10-14"),
    getBlob: () => ({ getDataAsString: () => "<h1>Valid HTML</h1>" }) };
}
function setup() {
  const root = folder("abcdefghijROOT123456789", "reports");
  const sub = folder("abcdefghijSUB123456789", "monthly", [root]);
  const other = folder("abcdefghijOUT123456789", "other");
  const good = file("abcdefghijHTML123456789", "report.html", [sub]);
  const outside = file("abcdefghijBAD123456789", "secret.html", [other]);
  const htmlSpoof = file("abcdefghijSPF123456789", "malware.html", [root], "text/plain");
  root.getFolders = () => iterator([sub]);
  root.getFiles = () => iterator([htmlSpoof]);
  sub.getFiles = () => iterator([good]);
  const folders = Object.fromEntries([root, sub, other].map(x => [x.getId(), x]));
  const files = Object.fromEntries([good, outside, htmlSpoof].map(x => [x.getId(), x]));
  const rendered = [];
  const output = content => ({ content, setTitle(title) { this.title = title; return this; } });
  const context = vm.createContext({
    DriveApp: {
      getFolderById: id => { if (!folders[id]) throw Error("Missing"); return folders[id]; },
      getFileById: id => { if (!files[id]) throw Error("Missing"); return files[id]; },
    },
    HtmlService: {
      createHtmlOutput: output,
      createTemplateFromFile(name) {
        assert.equal(name, "Index");
        const result = { evaluate() { rendered.push(result); return output("INDEX"); } };
        return result;
      },
    },
    ScriptApp: { getService: () => ({ getUrl: () => "https://script.google.com/macros/s/DEPLOY/exec" }) },
  });
  vm.runInContext(code, context);
  return { context, rendered };
}

test("indexes folder, filters non-HTML and links by Drive ID", () => {
  const { context, rendered } = setup();
  assert.equal(context.doGet({ parameter: {} }).content, "INDEX");
  assert.deepEqual(Array.from(rendered[0].entries, x => x.name), ["monthly"]);
  assert.match(rendered[0].entries[0].url, /\?dir=abcdefghijSUB123456789$/);
  assert.equal(context.doGet({ parameter: { dir: "abcdefghijSUB123456789" } }).content, "INDEX");
  assert.match(rendered[1].entries[0].url, /\?file=abcdefghijHTML123456789$/);
});

test("serves only HTML descendants, denying valid IDs outside root", () => {
  const { context } = setup();
  assert.equal(context.doGet({ parameter: { file: "abcdefghijHTML123456789" } }).content, "<h1>Valid HTML</h1>");
  for (const id of ["abcdefghijBAD123456789", "abcdefghijSPF123456789"]) {
    assert.equal(context.doGet({ parameter: { file: id } }).content, "<p>Page unavailable.</p>");
  }
  assert.equal(context.doGet({ parameter: { dir: "abcdefghijOUT123456789" } }).content, "<p>Page unavailable.</p>");
});

test("rejects invalid, ambiguous and repeated query parameters", () => {
  const { context } = setup();
  for (const param of [{ file: "../bad.html" }, { file: "", dir: "abcdefghijSUB123456789" },
    { file: "abcdefghijHTML123456789", dir: "abcdefghijSUB123456789" }, { unexpected: "yes" }]) {
    assert.equal(context.doGet({ parameter: param }).content, "<p>Page unavailable.</p>");
  }
  assert.equal(context.doGet({ parameter: { file: "abcdefghijHTML123456789" },
    parameters: { file: ["one", "two"] } }).content, "<p>Page unavailable.</p>");
});

test("index uses contextual escaping and top-level navigation", () => {
  const html = readFileSync(new URL("../../skills/gas-drive-html-server/templates/Index.html", import.meta.url), "utf8");
  assert.ok(html.includes("<?= entry.directory"));
  assert.ok(!html.includes("<?!="));
  assert.match(html, /<base target="_top">/);
});

test("deployer rejects unsafe arguments before any clasp operation", () => {
  const deployer = new URL("../../skills/gas-drive-html-server/scripts/deploy.mjs", import.meta.url);
  const result = spawnSync(process.execPath, [deployer.pathname, "--folder-id", "INVALID/ID",
    "--workdir", "/tmp/not-used", "--new-project", "Test"], { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /Valid --folder-id required/);
});