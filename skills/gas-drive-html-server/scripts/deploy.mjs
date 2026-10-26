#!/usr/bin/env node
// biome-ignore-all format: Preserve standalone, independently reviewed implementation.
// Self-contained clasp deployment for the gas-drive-html-server skill.
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { isDeepStrictEqual, parseArgs } from "node:util";

const templateDir = fileURLToPath(new URL("../templates/", import.meta.url));
const fileNames = ["Code.gs", "Index.html", "appsscript.json"];
const accessLevels = ["MYSELF", "DOMAIN", "ANYONE", "ANYONE_ANONYMOUS"];
const executeLevels = ["USER_DEPLOYING", "USER_ACCESSING"];
const validId = (value) =>
	typeof value === "string" && /^[A-Za-z0-9_-]{10,}$/.test(value);
const validDeploy = (value) =>
	typeof value === "string" && /^[A-Za-z0-9_-]+$/.test(value);
const check = (ok, message) => {
	if (!ok) throw Error(message);
};
const readJson = (file) => JSON.parse(fs.readFileSync(file, "utf8"));
const hash = (value) => createHash("sha256").update(value).digest("hex");
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const filesHash = (dir) =>
	Object.fromEntries(
		fileNames.map((name) => [
			name,
			hash(fs.readFileSync(path.join(dir, name))),
		]),
	);
const writeJson = (file, value) =>
	fs.writeFileSync(file, JSON.stringify(value, null, 2) + "\n", {
		mode: 0o600,
	});

let work;
let workCreated = false;
let stage = "validate";
let state = {};
let runner;
const localBin = fileURLToPath(
	new URL("../../../node_modules/.bin/", import.meta.url),
);
const save = () => {
	if (workCreated)
		writeJson(path.join(work, "deployment.json"), { ...state, stage });
};

function claspEnvironment() {
	const env = { ...process.env };
	for (const key of Object.keys(env)) {
		if (/^(DEBUG|NODE_OPTIONS|NODE_PATH|CLASP_CONFIG_.*)$/i.test(key))
			delete env[key];
	}
	if (fs.existsSync(localBin))
		env.PATH = [env.PATH, localBin].filter(Boolean).join(path.delimiter);
	return env;
}

function run(args, cwd, asJson = true, parseJsonOutput = asJson) {
	const env = claspEnvironment();
	if (!runner) {
		runner = [
			["pnpm", "exec", "clasp"],
			["npx", "--no-install", "--package=@google/clasp", "clasp"],
			["clasp"],
		].find(([exe, ...prefix]) => {
			const r = spawnSync(exe, [...prefix, "--version"], {
				cwd,
				env,
				encoding: "utf8",
				input: "",
			});
			return !r.error && r.status === 0;
		});
	}
	check(runner, "Official @google/clasp CLI was not found.");
	const [exe, ...prefix] = runner;
	const r = spawnSync(
		exe,
		[...prefix, ...(asJson ? ["--json"] : []), ...args],
		{
			cwd,
			env,
			encoding: "utf8",
			input: "",
			maxBuffer: 16 * 1024 * 1024,
		},
	);
	check(
		!r.error && r.status === 0,
		"clasp failed at " +
			stage +
			". Raw diagnostics withheld; check authentication, Apps Script API and permissions.",
	);
	if (!parseJsonOutput) return r.stdout;
	try {
		return JSON.parse(r.stdout);
	} catch {
		throw Error("Unexpected clasp JSON at " + stage);
	}
}

function clasp(
	dir,
	command,
	args = [],
	asJson = true,
	parseJsonOutput = asJson,
) {
	return run(
		[
			"--project",
			dir,
			"--ignore",
			path.join(work, ".claspignore"),
			command,
			...args,
		],
		dir,
		asJson,
		parseJsonOutput,
	);
}

function clone(scriptId, dir, version) {
	fs.mkdirSync(dir);
	const result = clasp(dir, "clone-script", [
		scriptId,
		...(version ? [String(version)] : []),
	]);
	check(
		Array.isArray(result.files) && result.files.length >= 3,
		"Incomplete remote project clone.",
	);
	const codeJs = path.join(dir, "Code.js");
	const codeGs = path.join(dir, "Code.gs");
	if (fs.existsSync(codeJs)) {
		check(
			!fs.existsSync(codeGs),
			"Refusing ambiguous Code.js and Code.gs files.",
		);
		fs.renameSync(codeJs, codeGs);
	}
	check(
		same(
			fs
				.readdirSync(dir)
				.filter((x) => x !== ".clasp.json")
				.sort(),
			[...fileNames].sort(),
		),
		"Refusing unmanaged GAS project or unexpected remote files.",
	);
	check(
		readJson(path.join(dir, ".clasp.json")).scriptId === scriptId,
		"Cloned project ID differs.",
	);
	check(
		fs
			.readFileSync(path.join(dir, "Code.gs"), "utf8")
			.startsWith("// Managed by gas-drive-html-server."),
		"Missing skill ownership marker.",
	);
	return filesHash(dir);
}

function policy(manifest) {
	const result = manifest.webapp;
	check(
		result &&
			accessLevels.includes(result.access) &&
			executeLevels.includes(result.executeAs),
		"Missing or invalid Web App policy.",
	);
	return { access: result.access, executeAs: result.executeAs };
}

function manifestSettings(manifest) {
	const { webapp, ...settings } = manifest;
	if (webapp) {
		const extraWebAppSettings = { ...webapp };
		delete extraWebAppSettings.access;
		delete extraWebAppSettings.executeAs;
		if (Object.keys(extraWebAppSettings).length)
			settings.webapp = extraWebAppSettings;
	}
	return settings;
}

function rootFolderId(dir) {
	const config = fs.readFileSync(path.join(dir, "Code.gs"), "utf8");
	const match = config.match(
		/^const ROOT_FOLDER_ID = (["'])([A-Za-z0-9_-]+)\1;$/m,
	);
	check(
		match && validId(match[2]),
		"Missing or invalid Drive root configuration.",
	);
	return match[2];
}

function parseJsonPrefix(output) {
	const text = output.trimStart();
	check(text.startsWith("{"), "Unable to inspect Web App metadata.");
	let depth = 0;
	let inString = false;
	let escaped = false;
	for (let i = 0; i < text.length; i++) {
		const character = text[i];
		if (inString) {
			if (escaped) escaped = false;
			else if (character === "\\") escaped = true;
			else if (character === '"') inString = false;
			continue;
		}
		if (character === '"') inString = true;
		else if (character === "{") depth++;
		else if (character === "}" && --depth === 0) {
			return {
				value: JSON.parse(text.slice(0, i + 1)),
				trailing: text.slice(i + 1).trim(),
			};
		}
	}
	throw Error("Unable to inspect Web App metadata.");
}

function verifiedUrl(dir, id) {
	const stdout = clasp(dir, "open-web-app", [id], true, false);
	const { value, trailing } = parseJsonPrefix(stdout);
	check(typeof value.url === "string", "Unable to inspect Web App metadata.");
	const url = new URL(value.url);
	check(
		trailing === `Open ${url.href} in your browser to continue.` ||
			trailing === `Opening ${url.href} in your browser.`,
		"Unexpected clasp output while inspecting Web App metadata.",
	);
	check(
		url.protocol === "https:" &&
			url.hostname === "script.google.com" &&
			url.pathname.endsWith("/s/" + id + "/exec") &&
			!url.search &&
			!url.hash,
		"Invalid production /exec URL.",
	);
	return url.href;
}

try {
	const argv = process.argv.slice(2);
	const flags = argv
		.filter((arg) => arg.startsWith("--"))
		.map((arg) => arg.split("=")[0]);
	check(new Set(flags).size === flags.length, "Duplicate CLI flag.");
	const { values: v } = parseArgs({
		options: {
			"folder-id": { type: "string" },
			workdir: { type: "string" },
			"new-project": { type: "string" },
			"script-id": { type: "string" },
			"deployment-id": { type: "string" },
			access: { type: "string" },
			"execute-as": { type: "string" },
			"acknowledge-exposure": { type: "boolean" },
			"allow-policy-change": { type: "boolean" },
			"allow-folder-change": { type: "boolean" },
			"exclusive-coordination": { type: "boolean" },
		},
	});
	const fresh = v["new-project"] !== undefined;
	check(validId(v["folder-id"]), "Valid --folder-id required.");
	check(
		typeof v.workdir === "string" && v.workdir !== "",
		"--workdir required.",
	);
	check(
		fresh !== (v["script-id"] !== undefined),
		"Specify one project target.",
	);
	check(
		fresh
			? !v["deployment-id"] && v["new-project"].trim() !== ""
			: validDeploy(v["script-id"]) &&
					validDeploy(v["deployment-id"]) &&
					v["exclusive-coordination"],
		"Updates require script/deployment IDs and exclusive coordination.",
	);
	check(
		Boolean(v.access) === Boolean(v["execute-as"]),
		"Provide --access and --execute-as together.",
	);
	const requested = v.access
		? { access: v.access, executeAs: v["execute-as"] }
		: null;
	check(
		!requested ||
			(accessLevels.includes(requested.access) &&
				executeLevels.includes(requested.executeAs)),
		"Invalid policy.",
	);
	check(
		!requested || requested.access === "MYSELF" || v["acknowledge-exposure"],
		"Non-private access requires --acknowledge-exposure.",
	);
	check(
		!fresh || (!v["allow-folder-change"] && !v["allow-policy-change"]),
		"Change-approval flags are update-only.",
	);

	work = path.resolve(v.workdir);
	check(
		!fs.existsSync(work) && fs.existsSync(path.dirname(work)),
		"Workdir must be fresh with an existing parent.",
	);
	fs.mkdirSync(work, { mode: 0o700 });
	workCreated = true;
	fs.writeFileSync(path.join(work, ".claspignore"), "");
	state = {
		folderId: v["folder-id"],
		scriptId: v["script-id"],
		deploymentId: v["deployment-id"],
		runtimeSmokeTest: "not performed",
	};
	save();
	const project = path.join(work, "project");
	fs.mkdirSync(project);
	let chosen;
	let before;
	let oldUrl;
	const templateManifest = readJson(path.join(templateDir, "appsscript.json"));

	if (fresh) {
		chosen = requested || { access: "MYSELF", executeAs: "USER_DEPLOYING" };
	} else {
		stage = "clone existing project";
		const snapshot = path.join(work, "snapshot");
		before = clone(state.scriptId, snapshot);
		const selected = clasp(snapshot, "list-deployments").find(
			(d) => d.deploymentId === state.deploymentId,
		);
		check(
			selected &&
				Number.isInteger(selected.versionNumber) &&
				selected.versionNumber > 0,
			"Deployment not found.",
		);
		const production = path.join(work, "production");
		clone(state.scriptId, production, selected.versionNumber);
		const productionManifest = readJson(
			path.join(production, "appsscript.json"),
		);
		const headManifest = readJson(path.join(snapshot, "appsscript.json"));
		const livePolicy = policy(productionManifest);
		const headPolicy = policy(headManifest);
		check(
			same(livePolicy, headPolicy),
			"Remote HEAD policy differs from production.",
		);
		const productionRoot = rootFolderId(production);
		const headRoot = rootFolderId(snapshot);
		chosen = requested || livePolicy;
		check(
			same(chosen, livePolicy) || v["allow-policy-change"],
			"Policy change requires --allow-policy-change.",
		);
		check(
			chosen.access === "MYSELF" || v["acknowledge-exposure"],
			"Non-private deployment requires --acknowledge-exposure.",
		);
		check(
			isDeepStrictEqual(
				manifestSettings(productionManifest),
				templateManifest,
			) && isDeepStrictEqual(manifestSettings(headManifest), templateManifest),
			"Remote manifest settings differ from the skill template; reconcile them before updating.",
		);
		check(
			[productionRoot, headRoot].every((rootId) => rootId === v["folder-id"]) ||
				v["allow-folder-change"],
			"Changing the Drive root requires --allow-folder-change.",
		);
		oldUrl = verifiedUrl(snapshot, state.deploymentId);
		fs.copyFileSync(
			path.join(snapshot, ".clasp.json"),
			path.join(project, ".clasp.json"),
		);
	}

	for (const name of fileNames) {
		let content = fs.readFileSync(path.join(templateDir, name), "utf8");
		if (name === "Code.gs") {
			check(
				content.includes("__ROOT_FOLDER_ID__"),
				"Missing template placeholder.",
			);
			content = content.replace("__ROOT_FOLDER_ID__", v["folder-id"]);
		}
		if (name === "appsscript.json") {
			content =
				JSON.stringify({ ...templateManifest, webapp: chosen }, null, 2) + "\n";
		}
		fs.writeFileSync(path.join(project, name), content);
	}
	state.policy = chosen;
	state.payloadSha256 = filesHash(project);
	save();

	if (fresh) {
		stage = "create project";
		const bootstrap = path.join(work, "bootstrap");
		fs.mkdirSync(bootstrap);
		state.creationAttempted = true;
		save();
		// A failed create may still create a remote script; never retry blindly.
		const output = clasp(
			bootstrap,
			"create-script",
			["--type", "standalone", "--title", v["new-project"]],
			false,
		);
		const match = output.match(
			/Created new script: https:\/\/script\.google\.com\/d\/([A-Za-z0-9_-]+)\/edit/,
		);
		const binding = path.join(bootstrap, ".clasp.json");
		const id = fs.existsSync(binding) ? readJson(binding).scriptId : match?.[1];
		check(
			validDeploy(id),
			"Creation may have succeeded; inspect bootstrap before retrying.",
		);
		state.scriptId = id;
		save();
		writeJson(path.join(project, ".clasp.json"), {
			scriptId: id,
			rootDir: ".",
		});
	} else {
		stage = "check remote consistency";
		check(
			same(before, clone(state.scriptId, path.join(work, "recheck"))),
			"Concurrent project modification; refusing push.",
		);
	}

	stage = "push";
	state.pushAttempted = true;
	save();
	const manifestChanged =
		fresh ||
		fs.readFileSync(path.join(work, "snapshot", "appsscript.json"), "utf8") !==
			fs.readFileSync(path.join(project, "appsscript.json"), "utf8");
	clasp(project, "push", manifestChanged ? ["--force"] : []);
	stage = "verify pushed files";
	check(
		same(
			state.payloadSha256,
			clone(state.scriptId, path.join(work, "readback")),
		),
		"Pushed payload mismatch.",
	);
	stage = "create version";
	const vInfo = clasp(project, "create-version", ["gas-drive-html-server"]);
	check(
		Number.isInteger(vInfo.versionNumber) && vInfo.versionNumber > 0,
		"Version number missing.",
	);
	state.version = vInfo.versionNumber;
	save();
	check(
		same(
			state.payloadSha256,
			clone(state.scriptId, path.join(work, "version"), state.version),
		),
		"Immutable version payload mismatch.",
	);
	stage = "deploy version";
	state.deploymentAttempted = true;
	save();
	const deployment = fresh
		? clasp(project, "create-deployment", [
				"--versionNumber",
				String(state.version),
				"--description",
				"gas-drive-html-server",
			])
		: clasp(project, "update-deployment", [
				state.deploymentId,
				"--versionNumber",
				String(state.version),
			]);
	check(
		validDeploy(deployment.deploymentId) &&
			(!state.deploymentId || state.deploymentId === deployment.deploymentId),
		"Deployment ID missing or changed.",
	);
	state.deploymentId = deployment.deploymentId;
	save();
	const live = clasp(project, "list-deployments").find(
		(d) => d.deploymentId === state.deploymentId,
	);
	check(
		live && live.versionNumber === state.version,
		"Deployment readback mismatch.",
	);
	state.url = verifiedUrl(project, state.deploymentId);
	check(
		!oldUrl || oldUrl === state.url,
		"Deployment URL unexpectedly changed.",
	);
	stage = "verified";
	save();
	console.log(JSON.stringify({ ...state, stage }, null, 2));
} catch (error) {
	state.failure = error.message;
	save();
	console.error(stage + ": " + error.message);
	process.exitCode = 1;
}
