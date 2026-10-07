import { test } from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const deploy = path.join(root, "skills/gas-html-artifact/scripts/deploy.sh");
const template = fs.readFileSync(
  path.join(root, "skills/gas-html-artifact/templates/Code.gs"),
  "utf8",
);
const manifest = {
  timeZone: "Etc/UTC",
  runtimeVersion: "V8",
  webapp: { access: "MYSELF", executeAs: "USER_DEPLOYING" },
};
const commands =
  "create-script clone-script push create-version create-deployment update-deployment list-deployments open-web-app show-authorized-user --json --project --ignore --force --versionNumber --type --title";
const mock = `#!/usr/bin/env node
const fs = require('fs'); const path = require('path');
const a = process.argv.slice(2); const dir = process.env.MOCK_REMOTE;
const commands = ${JSON.stringify(commands)}.split(' ');
const cmd = a.find(x => commands.includes(x) && !x.startsWith('--'));
const log = path.join(dir, 'calls.json'); const calls = JSON.parse(fs.readFileSync(log));
calls.push({cmd: cmd || a[0],args:a,cwd:process.cwd()}); fs.writeFileSync(log,JSON.stringify(calls));
if(a.includes('--version')) {console.log(process.env.MOCK_VERSION || '3.4.1'); process.exit(0);}
if(a.includes('--help')) {console.log(${JSON.stringify(commands)}); process.exit(0);}
if(a.includes('--project') && !fs.existsSync(a[a.indexOf('--project')+1])) {console.error('Invalid --project path: file or directory does not exist.');process.exit(12);}
if(process.env.MOCK_FAIL === cmd) {console.error('credential-token-must-not-leak'); process.exit(7);}
const load = file => JSON.parse(fs.readFileSync(path.join(dir,file)));
const save = (file,v) => fs.writeFileSync(path.join(dir,file),JSON.stringify(v));
const out = v => console.log(JSON.stringify(v));
const config = () => {const f=a[a.indexOf('--project')+1]; return JSON.parse(fs.readFileSync(f));};
const copy = obj => { for(const [name,bytes] of Object.entries(obj)) {fs.mkdirSync(path.dirname(name),{recursive:true}); fs.writeFileSync(name,bytes);} };
const list = load('deployments.json');
switch(cmd) {
 case 'show-authorized-user': out({loggedIn:process.env.MOCK_AUTH !== 'false'}); break;
 case 'create-script':
  console.log('Created new script: https://script.google.com/d/SCRIPT_NEW/edit');
  if(process.env.MOCK_CREATE_PULL_FAIL) process.exit(8);
  fs.writeFileSync('.clasp.json',JSON.stringify({scriptId:'SCRIPT_NEW',rootDir:'.'})); break;
 case 'clone-script': {
  const idx=a.indexOf(cmd); const id=a[idx+1]; const version=a[idx+2];
  if(id !== 'SCRIPT_NEW' && id !== 'SCRIPT_EXISTING') process.exit(9);
  let obj = version ? load('versions.json')[version] : load('files.json');
  if(process.env.MOCK_REMOTE_CHANGE && !version && calls.filter(c=>c.cmd===cmd&&!c.args.includes('--help')&&c.args.at(-1)==='SCRIPT_EXISTING').length===2) obj={...obj,'Concurrent.js':'const remoteChange=1;'};
  obj=Object.fromEntries(Object.entries(obj).map(([name,bytes])=>[name.replace(/\\.gs$/,'.js'),bytes]));
  copy(obj); fs.writeFileSync('.clasp.json',JSON.stringify({scriptId:id,rootDir:'.'}));
  if(process.env.MOCK_EMPTY_FILE) out({scriptId:id,files:[...Object.keys(obj),'Empty.js']});
  else out({scriptId:id,files:Object.keys(obj)}); break;
 }
 case 'list-deployments': config(); out(list); break;
 case 'open-web-app': {
  config(); const id=a[a.indexOf(cmd)+1];
  const url='https://script.google.com/macros/s/'+id+(process.env.MOCK_BAD_URL?'/dev':'/exec');
  out({url}); console.log('Open '+url+' in your browser to continue.'); break;
 }
 case 'push': {
  config(); const obj={};
  function collect(p='') { for(const e of fs.readdirSync(p||'.',{withFileTypes:true})) {const name=path.join(p,e.name); if(e.isDirectory())collect(name);else if(!e.name.startsWith('.'))obj[name]=fs.readFileSync(name,'utf8');} }
  collect(); if(!process.env.MOCK_SKIP_PUSH)save('files.json',obj); out(Object.keys(obj)); break;
 }
 case 'create-version': {const versions=load('versions.json'); versions['2']=load('files.json');save('versions.json',versions);out({versionNumber:2});break;}
 case 'create-deployment': list.push({deploymentId:'DEPLOY_NEW',versionNumber:2});save('deployments.json',list);out({deploymentId:'DEPLOY_NEW',versionNumber:2});break;
 case 'update-deployment': {const id=a[a.indexOf(cmd)+1]; const d=list.find(d=>d.deploymentId===id);if(!d)process.exit(10);d.versionNumber=2;save('deployments.json',list);out({deploymentId:id,versionNumber:2});break;}
 default: process.exit(11);
}
`;
function fixture(t, existing = false) {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), "gas artifact "));
  t.after(() => fs.rmSync(base, { recursive: true, force: true }));
  const bin = path.join(base, "bin");
  fs.mkdirSync(bin);
  fs.writeFileSync(path.join(bin, "clasp"), mock, { mode: 0o755 });
  const remote = path.join(base, "remote");
  fs.mkdirSync(remote);
  const put = (name, v) =>
    fs.writeFileSync(path.join(remote, name), JSON.stringify(v));
  const remoteFiles = existing
    ? {
        "Code.js": template,
        "Index.html": "<html>old</html>",
        "Other.js": "function useful(){ return 1; }",
        "Partial.html": "<b>keep</b>",
        "appsscript.json": JSON.stringify({
          ...manifest,
          oauthScopes: ["existing-scope"],
          dependencies: {
            enabledAdvancedServices: [
              { userSymbol: "Drive", serviceId: "drive", version: "v3" },
            ],
          },
        }),
      }
    : {};
  put("files.json", remoteFiles);
  put("calls.json", []);
  put(
    "deployments.json",
    existing ? [{ deploymentId: "DEPLOY_EXISTING", versionNumber: 1 }] : [],
  );
  put("versions.json", { 1: remoteFiles });
  const source = path.join(base, "my page.html");
  fs.writeFileSync(
    source,
    "<!doctype html>\r\n<html><body>hello</body></html>\r\n",
  );
  const bytes = fs.readFileSync(source);
  const sha = createHash("sha256").update(bytes).digest("hex");
  const report = path.join(base, "report.json");
  const assessment = {
    decision: "compatible",
    sourceSha256: sha,
    artifactSha256: sha,
    secretReview: "passed",
    evidence: ["self-contained browser HTML"],
    dependencies: [],
    transformations: [],
    limitations: ["no runtime test"],
    unresolved: [],
  };
  fs.writeFileSync(report, JSON.stringify(assessment));
  const work = path.join(base, "working directory");
  const args = [
    "--source",
    source,
    "--report",
    report,
    "--workdir",
    work,
    ...(existing
      ? [
          "--script-id",
          "SCRIPT_EXISTING",
          "--deployment-id",
          "DEPLOY_EXISTING",
          "--exclusive-coordination",
        ]
      : [
          "--new-project",
          "Test artifact",
          "--initial",
          "--access",
          "MYSELF",
          "--execute-as",
          "USER_DEPLOYING",
          "--allow-manifest-update",
        ]),
  ];
  const env = { PATH: `${bin}:${process.env.PATH}`, MOCK_REMOTE: remote };
  return {
    base,
    remote,
    source,
    report,
    assessment,
    work,
    args,
    put,
    run: (argv = args, extra = {}) =>
      spawnSync("/bin/bash", [deploy, ...argv], {
        encoding: "utf8",
        env: { ...env, ...extra },
      }),
    calls: () =>
      JSON.parse(fs.readFileSync(path.join(remote, "calls.json"))).filter(
        (c) => !c.args.includes("--help"),
      ),
    get: (name) => JSON.parse(fs.readFileSync(path.join(remote, name))),
  };
}
function without(args, ...names) {
  return args.filter(
    (value, i) =>
      !names.includes(value) &&
      !(i > 0 && names.includes(args[i - 1]) && !value.startsWith("--")),
  );
}
const mutations = (f) =>
  f
    .calls()
    .filter((c) =>
      [
        "create-script",
        "push",
        "create-version",
        "create-deployment",
        "update-deployment",
      ].includes(c.cmd),
    );

test("initial deployment preserves source bytes and verifies metadata", (t) => {
  const f = fixture(t);
  const result = f.run();
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(
    fs.readFileSync(path.join(f.work, "project/Index.html")),
    fs.readFileSync(f.source),
  );
  assert.deepEqual(Object.keys(f.get("files.json")).sort(), [
    "Code.gs",
    "Index.html",
    "appsscript.json",
  ]);
  const state = JSON.parse(
    fs.readFileSync(path.join(f.work, "deployment.json")),
  );
  assert.equal(state.url, "https://script.google.com/macros/s/DEPLOY_NEW/exec");
  assert.equal(state.scriptId, "SCRIPT_NEW");
  assert.equal(state.version, 2);
  assert.equal(state.runtimeSmokeTest, "not performed");
  assert.equal(
    f
      .calls()
      .find((c) => c.cmd === "push")
      .args.includes("--force"),
    true,
  );
});
test("update preserves unrelated complete payload, scopes/services, policy and URL", (t) => {
  const f = fixture(t, true);
  const before = f.get("files.json");
  const result = f.run();
  assert.equal(result.status, 0, result.stderr);
  const after = f.get("files.json");
  for (const name of ["Other.js", "Partial.html", "appsscript.json"])
    assert.equal(after[name], before[name]);
  assert.equal(
    f
      .calls()
      .some((c) => c.cmd === "create-script" || c.cmd === "create-deployment"),
    false,
  );
  assert.equal(
    f
      .calls()
      .find((c) => c.cmd === "push")
      .args.includes("--force"),
    false,
  );
  assert.deepEqual(f.get("deployments.json"), [
    { deploymentId: "DEPLOY_EXISTING", versionNumber: 2 },
  ]);
});
test("conversion deploys derivative while preserving original", (t) => {
  const f = fixture(t);
  const original = fs.readFileSync(f.source);
  const derivative = path.join(f.base, "derived.html");
  fs.writeFileSync(derivative, "<html>inlined supplied style</html>");
  f.assessment.decision = "convertible";
  f.assessment.transformations = ["inlined supplied stylesheet"];
  f.assessment.artifactSha256 = createHash("sha256")
    .update(fs.readFileSync(derivative))
    .digest("hex");
  fs.writeFileSync(f.report, JSON.stringify(f.assessment));
  const result = f.run([...f.args, "--derivative", derivative]);
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(fs.readFileSync(f.source), original);
  assert.deepEqual(
    fs.readFileSync(path.join(f.work, "project/Index.html")),
    fs.readFileSync(derivative),
  );
});
for (const [name, modify, env] of [
  [
    "missing source",
    (f) => {
      fs.unlinkSync(f.source);
      return f.args;
    },
  ],
  [
    "empty source",
    (f) => {
      fs.writeFileSync(f.source, "");
      return f.args;
    },
  ],
  [
    "directory source",
    (f) => {
      fs.unlinkSync(f.source);
      fs.mkdirSync(f.source);
      return f.args;
    },
  ],
  ["duplicate project option", (f) => [...f.args, "--new-project", "Other"]],
  ["conflicting project", (f) => [...f.args, "--script-id", "SCRIPT_EXISTING"]],
  [
    "conflicting deployment",
    (f) => [...f.args, "--deployment-id", "DEPLOY_EXISTING"],
  ],
  ["missing project", (f) => without(f.args, "--new-project")],
  ["missing deployment", (f) => without(f.args, "--initial")],
  ["invalid policy", (f) => f.args.map((x) => (x === "MYSELF" ? "PUBLIC" : x))],
  ["incomplete policy", (f) => without(f.args, "--execute-as")],
  [
    "manifest consent absent",
    (f) => without(f.args, "--allow-manifest-update"),
  ],
  ["old clasp", (f) => f.args, { MOCK_VERSION: "2.4.2" }],
  ["unauthenticated", (f) => f.args, { MOCK_AUTH: "false" }],
  [
    "unsupported report",
    (f) => {
      f.assessment.decision = "unsupported";
      fs.writeFileSync(f.report, JSON.stringify(f.assessment));
      return f.args;
    },
  ],
  [
    "uncertain report",
    (f) => {
      f.assessment.decision = "uncertain";
      fs.writeFileSync(f.report, JSON.stringify(f.assessment));
      return f.args;
    },
  ],
  [
    "unresolved dependency",
    (f) => {
      f.assessment.unresolved = ["missing asset"];
      fs.writeFileSync(f.report, JSON.stringify(f.assessment));
      return f.args;
    },
  ],
  [
    "stale assessment",
    (f) => {
      fs.appendFileSync(f.source, "changed");
      return f.args;
    },
  ],
  [
    "source output alias",
    (f) => {
      const args = [...f.args];
      args[args.indexOf("--workdir") + 1] = f.source;
      return args;
    },
  ],
  [
    "symlink alias",
    (f) => {
      fs.symlinkSync(f.source, f.work);
      return f.args;
    },
  ],
]) {
  test(`blocks ${name} before remote mutation`, (t) => {
    const f = fixture(t);
    const result = f.run(modify(f), env);
    assert.notEqual(result.status, 0);
    assert.equal(mutations(f).length, 0);
  });
}
for (const [name, modify, env] of [
  [
    "invalid deployment",
    (f) => f.args.map((x) => (x === "DEPLOY_EXISTING" ? "BAD" : x)),
  ],
  [
    "conflicting doGet",
    (f) => {
      const files = f.get("files.json");
      files["Other.js"] = "function doGet(){return 1;}";
      f.put("files.json", files);
      return f.args;
    },
  ],
  [
    "foreign Index ownership",
    (f) => {
      const files = f.get("files.json");
      files["Code.js"] = "function anotherApp(){}";
      f.put("files.json", files);
      return f.args;
    },
  ],
  ["missing coordination", (f) => without(f.args, "--exclusive-coordination")],
  ["remote change", (f) => f.args, { MOCK_REMOTE_CHANGE: "yes" }],
  ["skipped empty remote file", (f) => f.args, { MOCK_EMPTY_FILE: "yes" }],
]) {
  test(`existing project blocks ${name} before push`, (t) => {
    const f = fixture(t, true);
    const result = f.run(modify(f), env);
    assert.notEqual(result.status, 0);
    assert.equal(mutations(f).length, 0);
  });
}
for (const [failed, later] of [
  ["show-authorized-user", "create-script"],
  ["clone-script", "push"],
  ["push", "create-version"],
  ["create-version", "update-deployment"],
  ["update-deployment", "open-web-app"],
]) {
  test(`preserves ${failed} failure status and stops later stages`, (t) => {
    const f = fixture(t, true);
    const result = f.run(f.args, { MOCK_FAIL: failed });
    assert.equal(result.status, 7);
    assert.equal(
      result.stderr.includes("credential-token-must-not-leak"),
      false,
    );
    const callNames = f.calls().map((c) => c.cmd);
    const failedIndex = callNames.indexOf(failed);
    assert.equal(callNames.slice(failedIndex + 1).includes(later), false);
    if (failed === "create-version")
      assert.match(
        result.stderr,
        /Remote HEAD changed; selected production deployment was not advanced/,
      );
    if (failed === "update-deployment")
      assert.match(result.stderr, /deployment may have advanced/);
  });
}
test("partial creation records returned ID before subsequent retrieval fails", (t) => {
  const f = fixture(t);
  const result = f.run(f.args, { MOCK_CREATE_PULL_FAIL: "yes" });
  assert.equal(result.status, 8);
  assert.equal(
    JSON.parse(fs.readFileSync(path.join(f.work, "deployment.json"))).scriptId,
    "SCRIPT_NEW",
  );
  assert.equal(
    f.calls().some((c) => c.cmd === "push"),
    false,
  );
});
test("skipped push fails readback before version/deployment", (t) => {
  const f = fixture(t, true);
  const result = f.run(f.args, { MOCK_SKIP_PUSH: "yes" });
  assert.notEqual(result.status, 0);
  assert.equal(
    f.calls().some((c) => c.cmd === "create-version"),
    false,
  );
});
test("non-production URL fails verification and retains deployed ID", (t) => {
  const f = fixture(t);
  const result = f.run(f.args, { MOCK_BAD_URL: "yes" });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /deployment may have advanced/);
  assert.equal(
    JSON.parse(fs.readFileSync(path.join(f.work, "deployment.json")))
      .deploymentId,
    "DEPLOY_NEW",
  );
});
for (const mode of ["initial", "additional"]) {
  test(`existing project ${mode} preserves unrelated Code and manifest fields`, (t) => {
    const f = fixture(t, true);
    const remoteFiles = f.get("files.json");
    remoteFiles["Code.js"] = "function unrelated(){ return 3; }";
    delete remoteFiles["Index.html"];
    f.put("files.json", remoteFiles);
    if (mode === "initial") f.put("deployments.json", []);
    const args = without(f.args, "--deployment-id");
    args.push(
      `--${mode}`,
      "--access",
      "MYSELF",
      "--execute-as",
      "USER_DEPLOYING",
    );
    const result = f.run(args);
    assert.equal(result.status, 0, result.stderr);
    assert.equal(f.get("files.json")["Code.js"], remoteFiles["Code.js"]);
    assert.equal(f.get("files.json")["GasHtmlArtifact.gs"], template);
    assert.equal(
      f.get("files.json")["appsscript.json"],
      remoteFiles["appsscript.json"],
    );
  });
}
test("update uses selected version policy rather than remote HEAD policy", (t) => {
  const f = fixture(t, true);
  const remoteFiles = f.get("files.json");
  remoteFiles["appsscript.json"] = JSON.stringify({
    ...manifest,
    webapp: { access: "ANYONE", executeAs: "USER_ACCESSING" },
  });
  f.put("files.json", remoteFiles);
  const result = f.run([...f.args, "--allow-manifest-update"]);
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(
    JSON.parse(f.get("files.json")["appsscript.json"]).webapp,
    manifest.webapp,
  );
  assert.equal(
    f
      .calls()
      .find((c) => c.cmd === "push")
      .args.includes("--force"),
    true,
  );
});
test("caller-selected clasp config binds without touching its local project", (t) => {
  const f = fixture(t, true);
  const binding = path.join(f.base, "existing config.json");
  fs.writeFileSync(
    binding,
    JSON.stringify({ scriptId: "SCRIPT_EXISTING", rootDir: "/unrelated" }),
  );
  const original = fs.readFileSync(binding);
  const result = f.run([
    ...without(f.args, "--script-id"),
    "--clasp-config",
    binding,
  ]);
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(fs.readFileSync(binding), original);
});
