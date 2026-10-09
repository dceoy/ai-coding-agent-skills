import { test, type TestContext } from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../", import.meta.url));
const deploy = path.join(root, "skills/gas-html-artifact/scripts/deploy.mjs");
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
if(a.includes('--help')) {console.log(${JSON.stringify(commands)}.replace(process.env.MOCK_MISSING_CAPABILITY || '', '')); process.exit(0);}
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
  const url=(process.env.MOCK_URL || 'https://script.google.com/macros/s/{id}/exec').replace('{id}',id);
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
const mockRunner = `#!/usr/bin/env node
const fs = require('fs'); const path = require('path');
const { spawn } = require('child_process');
const runner = path.basename(process.argv[1]);
const argv = process.argv.slice(2);
fs.appendFileSync(path.join(process.env.MOCK_REMOTE, 'launchers.log'), runner + '\\n');
if(process.env.MOCK_RUNNER_FAIL === runner && !argv.includes('--version')) {console.error('secret-from-runner'); process.exit(23);}
if(process.env.MOCK_RUNNER_UNAVAILABLE === runner) process.exit(35);
let commandArgs;
if(runner === 'pnpm' && argv[0] === 'exec' && argv[1] === 'clasp') commandArgs = argv.slice(2);
else if(runner === 'npx' && argv[0] === '--no-install' && argv[1] === '--package=@google/clasp' && argv[2] === 'clasp') {
 if(process.env.MOCK_NPX_PACKAGE_MISSING) process.exit(36);
 commandArgs = argv.slice(3);
} else process.exit(34);
// npx resolves a package binary, not arbitrary executables from PATH.
const executable = runner === 'npx' ? path.join(path.dirname(process.argv[1]), 'clasp') : 'clasp';
const child = spawn(executable, commandArgs, {stdio:'inherit'});
child.on('error', () => process.exit(127));
child.on('close', code => process.exit(code ?? 1));
`;
function parseJSON(input: string | Buffer): any {
	return JSON.parse(input.toString());
}

function fixture(t: TestContext, existing = false) {
	const base = fs.realpathSync(
		fs.mkdtempSync(path.join(os.tmpdir(), "gas artifact ")),
	);
	t.after(() => fs.rmSync(base, { recursive: true, force: true }));
	const bin = path.join(base, "bin");
	fs.mkdirSync(bin);
	fs.writeFileSync(path.join(bin, "clasp"), mock, { mode: 0o755 });
	fs.symlinkSync(process.execPath, path.join(bin, "node"));
	for (const runner of ["pnpm", "npx"])
		fs.writeFileSync(path.join(bin, runner), mockRunner, { mode: 0o755 });
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
	fs.writeFileSync(path.join(remote, "launchers.log"), "");
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
	const assessment: {
		decision: string;
		sourceSha256: string;
		artifactSha256: string;
		secretReview: string;
		evidence: string[];
		dependencies: string[];
		transformations: string[];
		limitations: string[];
		unresolved: string[];
	} = {
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
	const env = { PATH: bin, MOCK_REMOTE: remote };
	return {
		base,
		bin,
		remote,
		source,
		report,
		assessment,
		work,
		args,
		put,
		run: (argv = args, extra = {}) =>
			spawnSync(process.execPath, [deploy, ...argv], {
				encoding: "utf8",
				env: { ...env, ...extra },
			}),
		launchers: () =>
			fs
				.readFileSync(path.join(remote, "launchers.log"), "utf8")
				.trim()
				.split("\n")
				.filter(Boolean),
		calls: () =>
			parseJSON(fs.readFileSync(path.join(remote, "calls.json"))).filter(
				(c) => !c.args.includes("--help"),
			),
		get: (name) => parseJSON(fs.readFileSync(path.join(remote, name))),
	};
}
function without(args: string[], ...names: string[]): string[] {
	return args.filter(
		(value, i) =>
			!names.includes(value) &&
			!(i > 0 && names.includes(args[i - 1]) && !value.startsWith("--")),
	);
}
const mutations = (f: ReturnType<typeof fixture>) =>
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

for (const [name, unavailable] of [
	["pnpm", []],
	["npx", ["pnpm"]],
	["clasp", ["pnpm", "npx"]],
] as Array<[string, string[]]>) {
	test(`uses ${name} for all clasp commands`, (t) => {
		const f = fixture(t);
		for (const runner of unavailable) fs.unlinkSync(path.join(f.bin, runner));
		const result = f.run();
		assert.equal(result.status, 0, result.stderr);
		assert.ok(f.calls().some((call) => call.cmd === "create-script"));
		const launched = f.launchers();
		if (name === "clasp") assert.deepEqual(launched, []);
		else {
			assert.ok(launched.length > 0);
			assert.ok(launched.every((runner) => runner === name));
		}
	});
}

test("does not fallback when pnpm exists but clasp execution fails", (t) => {
	const f = fixture(t);
	const result = f.run(f.args, { MOCK_RUNNER_FAIL: "pnpm" });
	assert.equal(result.status, 23);
	assert.ok(!result.stderr.includes("secret-from-runner"));
	assert.deepEqual(f.launchers(), ["pnpm", "pnpm"]);
	assert.deepEqual(
		f.calls().map((call) => call.cmd),
		["--version"],
	);
});

test("falls back to direct clasp when npx cannot resolve the official package", (t) => {
	const f = fixture(t);
	fs.unlinkSync(path.join(f.bin, "pnpm"));
	const result = f.run(f.args, { MOCK_NPX_PACKAGE_MISSING: "true" });
	assert.equal(result.status, 0, result.stderr);
	assert.deepEqual(f.launchers(), ["npx"]);
	assert.ok(f.calls().some((call) => call.cmd === "create-script"));
});

test("falls back when pnpm exists but cannot resolve clasp", (t) => {
	const f = fixture(t);
	const result = f.run(f.args, { MOCK_RUNNER_UNAVAILABLE: "pnpm" });
	assert.equal(result.status, 0, result.stderr);
	assert.equal(f.launchers()[0], "pnpm");
	assert.ok(
		f
			.launchers()
			.slice(1)
			.every((runner) => runner === "npx"),
	);
});

test("does not retry direct clasp after an actual npx command failure", (t) => {
	const f = fixture(t);
	fs.unlinkSync(path.join(f.bin, "pnpm"));
	const result = f.run(f.args, { MOCK_RUNNER_FAIL: "npx" });
	assert.equal(result.status, 23);
	assert.deepEqual(f.launchers(), ["npx", "npx"]);
	assert.deepEqual(
		f.calls().map((call) => call.cmd),
		["--version"],
	);
	assert.ok(!result.stderr.includes("secret-from-runner"));
});

test("real npx with an empty offline package cache falls back to PATH clasp", (t) => {
	const npx = (process.env.PATH || "")
		.split(path.delimiter)
		.map((directory) => path.join(directory, "npx"))
		.find((candidate) => fs.existsSync(candidate));
	if (!npx) {
		t.skip("npx is not installed in the test environment");
		return;
	}
	const f = fixture(t);
	fs.unlinkSync(path.join(f.bin, "pnpm"));
	fs.unlinkSync(path.join(f.bin, "npx"));
	fs.symlinkSync(npx, path.join(f.bin, "npx"));
	const result = f.run(f.args, {
		npm_config_cache: path.join(f.base, "empty-npm-cache"),
		npm_config_offline: "true",
		HOME: f.base,
	});
	assert.equal(result.status, 0, result.stderr);
	assert.ok(f.calls().some((call) => call.cmd === "create-script"));
	assert.ok(!fs.existsSync(path.join(f.work, "node_modules")));
});

test("clasp commands use one explicit ignore file", (t) => {
	const f = fixture(t);
	const result = f.run();
	assert.equal(result.status, 0, result.stderr);
	const calls = f
		.calls()
		.filter((call) =>
			["create-script", "clone-script", "push", "open-web-app"].includes(
				call.cmd,
			),
		);
	assert.ok(calls.length >= 4);
	for (const call of calls) {
		const index = call.args.indexOf("--ignore");
		assert.notEqual(index, -1);
		assert.equal(call.args[index + 1], path.join(f.work, "empty.claspignore"));
	}
});
test("clasp version is not restricted when required capabilities exist", (t) => {
	const f = fixture(t);
	const result = f.run(f.args, { MOCK_VERSION: "4.0.0" });
	assert.equal(result.status, 0, result.stderr);
});
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
	const state = parseJSON(
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
	[
		"unsupported clasp CLI",
		(f) => f.args,
		{ MOCK_MISSING_CAPABILITY: "open-web-app" },
	],
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
] as Array<
	[string, (f: ReturnType<typeof fixture>) => string[], Record<string, string>?]
>) {
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
] as Array<
	[string, (f: ReturnType<typeof fixture>) => string[], Record<string, string>?]
>) {
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
		parseJSON(fs.readFileSync(path.join(f.work, "deployment.json"))).scriptId,
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
for (const [name, url] of [
	["consumer", "https://script.google.com/macros/s/{id}/exec"],
	[
		"Workspace domain",
		"https://script.google.com/a/macros/example.com/s/{id}/exec",
	],
	[
		"Workspace domain-first",
		"https://script.google.com/a/example.com/macros/s/{id}/exec",
	],
	[
		"Workspace account selector",
		"https://script.google.com/a/~/macros/s/{id}/exec",
	],
]) {
	for (const existing of [false, true]) {
		test(`${name} URL is verified for ${existing ? "update" : "initial deployment"}`, (t) => {
			const f = fixture(t, existing);
			const result = f.run(f.args, { MOCK_URL: url });
			assert.equal(result.status, 0, result.stderr);
			const state = parseJSON(
				fs.readFileSync(path.join(f.work, "deployment.json")),
			);
			assert.equal(state.stage, "verified");
			assert.equal(state.url, url.replace("{id}", state.deploymentId));
			if (existing) assert.equal(state.previousURL, state.url);
		});
	}
}
for (const [name, url] of [
	["consumer dev", "https://script.google.com/macros/s/{id}/dev"],
	[
		"Workspace dev",
		"https://script.google.com/a/macros/example.com/s/{id}/dev",
	],
	[
		"Workspace domain-first dev",
		"https://script.google.com/a/example.com/macros/s/{id}/dev",
	],
	[
		"Workspace domain-first wrong deployment",
		"https://script.google.com/a/example.com/macros/s/OTHER/exec",
	],
	[
		"Workspace domain-first empty domain",
		"https://script.google.com/a//macros/s/{id}/exec",
	],
	[
		"Workspace domain-first extra segment",
		"https://script.google.com/a/example.com/extra/macros/s/{id}/exec",
	],
	[
		"wrong deployment",
		"https://script.google.com/a/macros/example.com/s/OTHER/exec",
	],
	["empty domain", "https://script.google.com/a/macros//s/{id}/exec"],
	[
		"extra domain segment",
		"https://script.google.com/a/macros/example.com/extra/s/{id}/exec",
	],
	[
		"extra path segment",
		"https://script.google.com/a/macros/example.com/s/{id}/exec/extra",
	],
	["wrong host", "https://example.com/a/macros/example.com/s/{id}/exec"],
	["HTTP", "http://script.google.com/a/macros/example.com/s/{id}/exec"],
	[
		"credentials",
		"https://user:password@script.google.com/a/macros/example.com/s/{id}/exec",
	],
]) {
	test(`${name} URL fails verification and retains deployed ID`, (t) => {
		const f = fixture(t);
		const result = f.run(f.args, { MOCK_URL: url });
		assert.notEqual(result.status, 0);
		assert.match(result.stderr, /Metadata did not confirm a production/);
		assert.match(result.stderr, /deployment may have advanced/);
		assert.equal(
			parseJSON(fs.readFileSync(path.join(f.work, "deployment.json")))
				.deploymentId,
			"DEPLOY_NEW",
		);
	});
}
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
		parseJSON(f.get("files.json")["appsscript.json"]).webapp,
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
for (const consent of [false, true]) {
	test(`production policy change with HEAD already changed requires consent (${consent})`, (t) => {
		const f = fixture(t, true);
		const requested = { access: "ANYONE", executeAs: "USER_ACCESSING" };
		const remoteFiles = f.get("files.json");
		remoteFiles["appsscript.json"] = JSON.stringify({
			...manifest,
			webapp: requested,
		});
		f.put("files.json", remoteFiles);
		const args = [
			...f.args,
			"--access",
			requested.access,
			"--execute-as",
			requested.executeAs,
			...(consent ? ["--allow-manifest-update"] : []),
		];
		const result = f.run(args);
		assert.equal(result.status, consent ? 0 : 1, result.stderr);
		assert.equal(
			f.calls().some((c) => c.cmd === "update-deployment"),
			consent,
		);
		assert.equal(
			f.calls().some((c) => c.cmd === "push" && c.args.includes("--force")),
			false,
		);
		assert.deepEqual(f.get("deployments.json"), [
			{ deploymentId: "DEPLOY_EXISTING", versionNumber: consent ? 2 : 1 },
		]);
	});
}
