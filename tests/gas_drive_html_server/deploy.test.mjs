// biome-ignore-all format: Preserve standalone, independently reviewed tests.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const root = fileURLToPath(new URL("../../", import.meta.url));
const sourceDeploy = path.join(
	root,
	"skills/gas-drive-html-server/scripts/deploy.mjs",
);
const sourceTemplates = path.join(root, "skills/gas-drive-html-server/templates");
const rootA = "abcdefghijROOT000000000001";
const rootB = "abcdefghijROOT000000000002";
const deploymentUrl = "https://script.google.com/macros/s/DEPLOY_EXISTING/exec";
const templateManifest = JSON.parse(
	fs.readFileSync(path.join(sourceTemplates, "appsscript.json"), "utf8"),
);
const manifest = {
	...templateManifest,
	webapp: { access: "MYSELF", executeAs: "USER_DEPLOYING" },
};
const manifestText = (value) => JSON.stringify(value, null, 2) + "\n";

const mockClasp = `#!${process.execPath}
const fs = require("node:fs");
const path = require("node:path");
const args = process.argv.slice(2);
const remote = process.env.MOCK_REMOTE;
const commands = ["create-script", "clone-script", "push", "create-version", "create-deployment", "update-deployment", "list-deployments", "open-web-app"];
const command = args.find((value) => commands.includes(value));
const read = (name) => JSON.parse(fs.readFileSync(path.join(remote, name), "utf8"));
const write = (name, value) => fs.writeFileSync(path.join(remote, name), JSON.stringify(value));
const output = (value) => console.log(JSON.stringify(value));

if (args.includes("--version")) {
  console.log("3.4.1");
  process.exit(0);
}
if (!command) process.exit(11);

const projectPath = args[args.indexOf("--project") + 1];
const ignorePath = args[args.indexOf("--ignore") + 1];
const projectExists = Boolean(projectPath && fs.existsSync(projectPath));
const projectIsDirectory = projectExists && fs.statSync(projectPath).isDirectory();
const projectDir = projectIsDirectory ? projectPath : path.dirname(projectPath);
const call = {
  command,
  args,
  cwd: process.cwd(),
  projectPath,
  projectExists,
  projectIsDirectory,
  hasJson: args.includes("--json"),
  path: process.env.PATH,
};
fs.appendFileSync(path.join(remote, "calls.json"), JSON.stringify(call) + "\\n");
if (!projectExists || !fs.existsSync(ignorePath)) process.exit(12);
if (["create-script", "clone-script"].includes(command) && !projectIsDirectory) process.exit(13);

const deployments = () => read("deployments.json");
const fileMap = () => read("current.json");
const binding = () => JSON.parse(fs.readFileSync(path.join(projectDir, ".clasp.json"), "utf8"));
if (command === "create-script") {
  const scriptId = "SCRIPT_NEW";
  fs.writeFileSync(path.join(projectDir, ".clasp.json"), JSON.stringify({ scriptId, rootDir: "." }));
  console.log("Created new script: https://script.google.com/d/" + scriptId + "/edit");
} else if (command === "clone-script") {
  const index = args.indexOf(command);
  const scriptId = args[index + 1];
  const version = args[index + 2];
  const versionFiles = version ? read("versions.json")[version] : undefined;
  const files = version ? versionFiles : fileMap();
  if (!files || scriptId !== "SCRIPT_NEW" && scriptId !== "SCRIPT_EXISTING") process.exit(14);
  const localFiles = {};
  for (const [name, content] of Object.entries(files)) {
    const localName = name.endsWith(".gs") ? name.slice(0, -3) + ".js" : name;
    localFiles[localName] = content;
  }
  if (process.env.MOCK_CLONE_MODE === "extra") localFiles["Unexpected.html"] = "<p>unmanaged</p>";
  if (process.env.MOCK_CLONE_MODE === "missing-code") delete localFiles["Code.js"];
  if (process.env.MOCK_CLONE_MODE === "unowned") localFiles["Code.js"] = "function notManaged() {}";
  if (process.env.MOCK_CLONE_MODE === "duplicate") localFiles["Code.gs"] = localFiles["Code.js"];
  for (const [name, content] of Object.entries(localFiles)) {
    fs.writeFileSync(path.join(process.cwd(), name), content);
  }
  fs.writeFileSync(path.join(process.cwd(), ".clasp.json"), JSON.stringify({ scriptId, rootDir: "." }));
  output({ files: Object.keys(localFiles) });
} else if (command === "push") {
  binding();
  const files = {};
  for (const name of fs.readdirSync(projectDir)) {
    if (!name.startsWith(".")) files[name] = fs.readFileSync(path.join(projectDir, name), "utf8");
  }
  if (files["appsscript.json"] !== fileMap()["appsscript.json"] && !args.includes("--force")) {
    process.exit(0);
  }
  write("current.json", files);
  output(Object.keys(files));
} else if (command === "create-version") {
  binding();
  const versions = read("versions.json");
  const number = Math.max(0, ...Object.keys(versions).map(Number)) + 1;
  versions[String(number)] = fileMap();
  write("versions.json", versions);
  output({ versionNumber: number });
} else if (command === "create-deployment") {
  binding();
  const versionNumber = Number(args[args.indexOf("--versionNumber") + 1]);
  const deploymentId = "DEPLOY_NEW";
  const list = deployments();
  list.push({ deploymentId, versionNumber });
  write("deployments.json", list);
  output({ deploymentId, versionNumber });
} else if (command === "update-deployment") {
  binding();
  const index = args.indexOf(command);
  const deploymentId = args[index + 1];
  const versionNumber = Number(args[args.indexOf("--versionNumber") + 1]);
  const list = deployments();
  const selected = list.find((item) => item.deploymentId === deploymentId);
  if (!selected) process.exit(15);
  selected.versionNumber = versionNumber;
  write("deployments.json", list);
  output({ deploymentId, versionNumber });
} else if (command === "list-deployments") {
  binding();
  output(deployments());
} else if (command === "open-web-app") {
  binding();
  const deploymentId = args[args.indexOf(command) + 1];
  const url = "https://script.google.com/macros/s/" + deploymentId + "/exec";
  if (args.includes("--json")) {
    console.log(JSON.stringify({ url }, null, 2));
    console.log(process.env.MOCK_BROWSER === "true"
      ? "Opening " + url + " in your browser."
      : "Open " + url + " in your browser to continue.");
  } else {
    console.log("Open " + url + " in your browser to continue.");
  }
}
`;

function codeWithRoot(template, folderId) {
	if (folderId === null) {
		return template.replace(/^const ROOT_FOLDER_ID = .*;\n/m, "");
	}
	return template.replace("__ROOT_FOLDER_ID__", folderId);
}

function fixture(t, options = {}) {
	const base = fs.mkdtempSync(path.join(os.tmpdir(), "gas drive server "));
	t.after(() => fs.rmSync(base, { recursive: true, force: true }));
	const bundle = path.join(base, "bundle");
	const deployDir = path.join(bundle, "skills/gas-drive-html-server/scripts");
	const templateDir = path.join(bundle, "skills/gas-drive-html-server/templates");
	const localBin = path.join(bundle, "node_modules/.bin");
	const toolPath = path.join(base, "empty-path");
	const remote = path.join(base, "remote");
	const work = path.join(base, options.existing ? "update-work" : "new-work");
	fs.mkdirSync(deployDir, { recursive: true });
	fs.mkdirSync(templateDir, { recursive: true });
	fs.mkdirSync(localBin, { recursive: true });
	fs.mkdirSync(toolPath);
	fs.mkdirSync(remote);
	fs.copyFileSync(sourceDeploy, path.join(deployDir, "deploy.mjs"));
	for (const name of ["Code.gs", "Index.html", "appsscript.json"])
		fs.copyFileSync(path.join(sourceTemplates, name), path.join(templateDir, name));
	fs.writeFileSync(path.join(localBin, "clasp"), mockClasp, { mode: 0o755 });

	const template = fs.readFileSync(path.join(sourceTemplates, "Code.gs"), "utf8");
	const headRoot = Object.hasOwn(options, "headRoot") ? options.headRoot : rootA;
	const productionRoot = Object.hasOwn(options, "productionRoot")
		? options.productionRoot
		: headRoot;
	const headManifest = options.headManifest ?? manifest;
	const productionManifest = options.productionManifest ?? headManifest;
	const headManifestText =
		options.headManifestText ?? manifestText(headManifest);
	const productionManifestText =
		options.productionManifestText ?? manifestText(productionManifest);
	const existingFiles = options.existing
		? {
				"Code.gs": codeWithRoot(template, headRoot),
				"Index.html": "<html>existing</html>",
				"appsscript.json": headManifestText,
			}
		: {};
	const deployedFiles = options.existing
		? {
				...existingFiles,
				"Code.gs": codeWithRoot(template, productionRoot),
				"appsscript.json": productionManifestText,
			}
		: {};
	fs.writeFileSync(path.join(remote, "calls.json"), "");
	fs.writeFileSync(path.join(remote, "current.json"), JSON.stringify(existingFiles));
	fs.writeFileSync(
		path.join(remote, "versions.json"),
		JSON.stringify(options.existing ? { "1": deployedFiles } : {}),
	);
	fs.writeFileSync(
		path.join(remote, "deployments.json"),
		JSON.stringify(options.existing ? [{ deploymentId: "DEPLOY_EXISTING", versionNumber: 1 }] : []),
	);

	const run = (args, extraEnv = {}) =>
		spawnSync(process.execPath, [path.join(deployDir, "deploy.mjs"), ...args], {
			encoding: "utf8",
			env: {
				...process.env,
				PATH: toolPath,
				MOCK_REMOTE: remote,
				...(options.cloneMode ? { MOCK_CLONE_MODE: options.cloneMode } : {}),
				...(options.browserPresent ? { MOCK_BROWSER: "true" } : {}),
				...extraEnv,
			},
		});
	const newArgs = () => [
		"--folder-id",
		rootA,
		"--workdir",
		work,
		"--new-project",
		"Drive HTML directory",
	];
	const updateArgs = (folderId = rootA, allowFolderChange = false, extra = []) => [
		"--folder-id",
		folderId,
		"--workdir",
		work,
		"--script-id",
		"SCRIPT_EXISTING",
		"--deployment-id",
		"DEPLOY_EXISTING",
		"--exclusive-coordination",
		...(allowFolderChange ? ["--allow-folder-change"] : []),
		...extra,
	];
	return {
		base,
		localBin,
		work,
		run,
		newArgs,
		updateArgs,
		calls: () => fs.readFileSync(path.join(remote, "calls.json"), "utf8").trim().split("\n").filter(Boolean).map(JSON.parse),
		state: () => JSON.parse(fs.readFileSync(path.join(work, "deployment.json"), "utf8")),
		remote: (name) => JSON.parse(fs.readFileSync(path.join(remote, name), "utf8")),
	};
}

test("fresh deployment creates and verifies using the local clasp and normalized Code.js clones", (t) => {
	const f = fixture(t);
	const result = f.run(f.newArgs());
	assert.equal(result.status, 0, result.stderr);
	const output = JSON.parse(result.stdout);
	assert.equal(output.stage, "verified");
	assert.equal(output.scriptId, "SCRIPT_NEW");
	assert.equal(output.deploymentId, "DEPLOY_NEW");
	assert.equal(output.url, "https://script.google.com/macros/s/DEPLOY_NEW/exec");
	const calls = f.calls();
	const create = calls.find((call) => call.command === "create-script");
	const push = calls.find((call) => call.command === "push");
	assert.equal(create.projectPath, create.cwd);
	assert.equal(create.projectIsDirectory, true);
	assert.ok(push.args.includes("--force"));
	const clones = calls.filter((call) => call.command === "clone-script");
	assert.ok(clones.length >= 2);
	assert.ok(clones.every((call) => call.projectIsDirectory));
	assert.ok(
		calls.every((call) =>
			call.path
				.split(path.delimiter)
				.some((entry) => path.resolve(entry) === path.resolve(f.localBin)),
		),
		JSON.stringify(calls.map((call) => [call.path, f.localBin])),
	);
	assert.ok(calls.some((call) => call.command === "open-web-app" && call.hasJson));
	assert.ok(f.remote("current.json")["Code.gs"].includes(`const ROOT_FOLDER_ID = '${rootA}';`));
});

test("existing deployment normalizes Code.js clones and retains its URL and deployment ID", (t) => {
	const f = fixture(t, { existing: true, browserPresent: true });
	const result = f.run(f.updateArgs());
	assert.equal(result.status, 0, result.stderr);
	const output = JSON.parse(result.stdout);
	assert.equal(output.stage, "verified");
	assert.equal(output.deploymentId, "DEPLOY_EXISTING");
	assert.equal(output.url, deploymentUrl);
	assert.equal(f.remote("deployments.json")[0].deploymentId, "DEPLOY_EXISTING");
	assert.ok(f.calls().filter((call) => call.command === "clone-script").length >= 4);
	assert.ok(f.calls().filter((call) => call.command === "open-web-app").every((call) => call.hasJson));
	assert.equal(
		f.calls().find((call) => call.command === "push").args.includes("--force"),
		false,
	);
});

test("existing deployment forces formatting-only manifest normalization", (t) => {
	const compactManifest = JSON.stringify(manifest);
	const f = fixture(t, {
		existing: true,
		headManifestText: compactManifest,
		productionManifestText: compactManifest,
	});
	const result = f.run(f.updateArgs());
	assert.equal(result.status, 0, result.stderr);
	assert.equal(f.state().stage, "verified");
	assert.ok(
		f.calls()
			.find((call) => call.command === "push")
			.args.includes("--force"),
	);
	assert.equal(
		f.remote("current.json")["appsscript.json"],
		manifestText(manifest),
	);
	assert.equal(f.remote("deployments.json")[0].deploymentId, "DEPLOY_EXISTING");
});

test("an approved policy change forces the manifest push and retains deployment identity", (t) => {
	const f = fixture(t, { existing: true });
	const result = f.run(
		f.updateArgs(rootA, false, [
			"--access",
			"DOMAIN",
			"--execute-as",
			"USER_DEPLOYING",
			"--allow-policy-change",
			"--acknowledge-exposure",
		]),
	);
	assert.equal(result.status, 0, result.stderr);
	assert.equal(f.state().stage, "verified");
	assert.ok(
		f.calls()
			.find((call) => call.command === "push")
			.args.includes("--force"),
	);
	assert.equal(f.state().deploymentId, "DEPLOY_EXISTING");
	assert.equal(f.state().url, deploymentUrl);
});

const customManifestCases = [
	{
		name: "missing HEAD scope configuration",
		headManifest: Object.fromEntries(
			Object.entries(manifest).filter(([name]) => name !== "oauthScopes"),
		),
	},
	{
		name: "custom production scopes",
		productionManifest: {
			...manifest,
			oauthScopes: [...manifest.oauthScopes, "https://www.googleapis.com/auth/script.external_request"],
		},
	},
	{
		name: "custom HEAD manifest field",
		headManifest: { ...manifest, dependencies: { enabledAdvancedServices: [] } },
	},
	{
		name: "custom production Web App field",
		productionManifest: {
			...manifest,
			webapp: { ...manifest.webapp, executeApi: "MYSELF" },
		},
	},
];

for (const scenario of customManifestCases) {
	test(`manifest validation rejects ${scenario.name}`, (t) => {
		const f = fixture(t, { existing: true, ...scenario });
		const beforeFiles = f.remote("current.json");
		const beforeDeployments = f.remote("deployments.json");
		const result = f.run(
			f.updateArgs(rootA, true, ["--allow-policy-change"]),
		);
		assert.equal(result.status, 1);
		assert.equal(f.state().stage, "clone existing project");
		assert.match(f.state().failure, /Remote manifest settings differ/);
		assert.equal(f.calls().some((call) => call.command === "push"), false);
		assert.equal(f.calls().some((call) => call.command === "create-version"), false);
		assert.deepEqual(f.remote("current.json"), beforeFiles);
		assert.deepEqual(f.remote("deployments.json"), beforeDeployments);
	});
}

const rootAuthorizationCases = [
	{
		name: "unchanged production and HEAD roots succeed",
		headRoot: rootA,
		productionRoot: rootA,
		requestedRoot: rootA,
		allow: false,
		status: 0,
		stage: "verified",
		pushed: true,
		url: deploymentUrl,
	},
	{
		name: "a request matching HEAD but changing production needs approval",
		headRoot: rootB,
		productionRoot: rootA,
		requestedRoot: rootB,
		allow: false,
		status: 1,
		stage: "clone existing project",
		pushed: false,
		url: null,
	},
	{
		name: "a request matching production but changing HEAD needs approval",
		headRoot: rootA,
		productionRoot: rootB,
		requestedRoot: rootA,
		allow: false,
		status: 1,
		stage: "clone existing project",
		pushed: false,
		url: null,
	},
	{
		name: "an explicitly approved root change succeeds",
		headRoot: rootB,
		productionRoot: rootA,
		requestedRoot: rootB,
		allow: true,
		status: 0,
		stage: "verified",
		pushed: true,
		url: deploymentUrl,
	},
];

for (const scenario of rootAuthorizationCases) {
	test(`root authorization: ${scenario.name}`, (t) => {
		const f = fixture(t, {
			existing: true,
			headRoot: scenario.headRoot,
			productionRoot: scenario.productionRoot,
		});
		const result = f.run(f.updateArgs(scenario.requestedRoot, scenario.allow));
		const state = f.state();
		assert.equal(result.status, scenario.status, result.stderr);
		assert.equal(state.stage, scenario.stage);
		assert.equal(state.deploymentId, "DEPLOY_EXISTING");
		assert.equal(state.url ?? null, scenario.url);
		assert.equal(f.calls().some((call) => call.command === "push"), scenario.pushed);
	});
}

const invalidRootCases = [
	{ name: "missing HEAD root", headRoot: null, productionRoot: rootA, allow: false },
	{ name: "short HEAD root remains invalid with approval", headRoot: "short", productionRoot: rootA, allow: true },
	{ name: "missing production root", headRoot: rootA, productionRoot: null, allow: false },
	{ name: "short production root remains invalid with approval", headRoot: rootA, productionRoot: "short", allow: true },
];

for (const scenario of invalidRootCases) {
	test(`root authorization rejects ${scenario.name}`, (t) => {
		const f = fixture(t, {
			existing: true,
			headRoot: scenario.headRoot,
			productionRoot: scenario.productionRoot,
		});
		const result = f.run(f.updateArgs(rootA, scenario.allow));
		assert.equal(result.status, 1);
		assert.match(f.state().failure, /Missing or invalid Drive root configuration/);
		assert.equal(f.calls().some((call) => call.command === "push"), false);
	});
}

const cloneValidationCases = [
	{ name: "extra files", mode: "extra", error: /Refusing unmanaged GAS project/ },
	{ name: "missing server file", mode: "missing-code", error: /Incomplete remote project clone/ },
	{ name: "unowned server file", mode: "unowned", error: /Missing skill ownership marker/ },
	{ name: "both server extensions", mode: "duplicate", error: /ambiguous Code\.js and Code\.gs/ },
];

for (const scenario of cloneValidationCases) {
	test(`clone validation rejects ${scenario.name}`, (t) => {
		const f = fixture(t, { existing: true, cloneMode: scenario.mode });
		const result = f.run(f.updateArgs());
		assert.equal(result.status, 1);
		assert.match(f.state().failure, scenario.error);
		assert.equal(f.calls().some((call) => call.command === "push"), false);
	});
}
