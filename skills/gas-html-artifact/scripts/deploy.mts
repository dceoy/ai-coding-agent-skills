#!/usr/bin/env node
// Deterministic packaging only. Compatibility assessment belongs to the agent.
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { spawn, spawnSync } from "node:child_process";
import { parseArgs } from "node:util";

/** Validated Web App deployment permissions. */
type Policy = {
	access: (typeof accessValues)[number];
	executeAs: (typeof executeValues)[number];
};

type Artifact = { path: string; bytes: Buffer; sha256: string };

/** Persisted recovery information, including partial deployment stages. */
type DeploymentState = {
	stage: string;
	scriptId?: string;
	deploymentId?: string;
	version?: number;
	source: { path: string; sha256: string };
	artifact: { path: string; sha256: string };
	report: string;
	runtimeSmokeTest: string;
	previousURL?: string;
	previousPolicy?: Policy | null;
	policy?: Policy;
	files?: string[];
	payloadSha256?: Record<string, string>;
	url?: string;
	failedStage?: string;
};

const templates = fileURLToPath(new URL("../templates/", import.meta.url));
const accessValues = [
	"MYSELF",
	"DOMAIN",
	"ANYONE",
	"ANYONE_ANONYMOUS",
] as const;
const executeValues = ["USER_ACCESSING", "USER_DEPLOYING"] as const;
let stage = "local validation";
let work!: string;
let state!: DeploymentState;
let pushed = false;
let deploymentAttempted = false;
let pushAttempted = false;
const claspLaunchers = [
	{ executable: "pnpm", prefix: ["exec", "clasp"] },
	{
		executable: "npx",
		prefix: ["--no-install", "--package=@google/clasp", "clasp"],
	},
	{ executable: "clasp", prefix: [] },
];
let selectedClaspLauncher: (typeof claspLaunchers)[number] | undefined;
function requireThat(condition: unknown, message: string): asserts condition {
	if (!condition) throw new Error(message);
}
function parseJSON(text: string): any {
	try {
		return JSON.parse(text);
	} catch {
		throw new Error("Invalid JSON; contents withheld.");
	}
}
function json(file: string): any {
	return parseJSON(fs.readFileSync(file, "utf8"));
}
function digest(bytes: Buffer | string): string {
	return createHash("sha256").update(bytes).digest("hex");
}
function writeJSON(file: string, value: unknown): void {
	const temporary = `${file}.tmp`;
	fs.writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, {
		mode: 0o600,
		flag: "wx",
	});
	fs.renameSync(temporary, file);
}
function identifier(value: unknown): value is string {
	return typeof value === "string" && /^[A-Za-z0-9_-]+$/.test(value);
}
function readArtifact(file: string): Artifact {
	const resolved = fs.realpathSync(file);
	requireThat(
		fs.statSync(resolved).isFile(),
		"Artifact must be a readable file.",
	);
	const bytes = fs.readFileSync(resolved);
	new TextDecoder("utf-8", { fatal: true }).decode(bytes);
	requireThat(
		bytes.length > 0 && /\.html?$/i.test(resolved),
		"Artifact must be non-empty HTML.",
	);
	return { path: resolved, bytes, sha256: digest(bytes) };
}
function inside(parent: string, child: string): boolean {
	return child === parent || child.startsWith(`${parent}${path.sep}`);
}
function files(root: string, prefix = ""): string[] {
	return fs
		.readdirSync(path.join(root, prefix), { withFileTypes: true })
		.flatMap((entry) => {
			const name = path.join(prefix, entry.name);
			requireThat(
				!entry.isSymbolicLink(),
				"Symlinks are forbidden in the staged payload.",
			);
			if (entry.isDirectory()) return files(root, name);
			requireThat(entry.isFile(), "Non-regular staged file.");
			return [name];
		})
		.sort();
}
function payload(root: string): Record<string, string> {
	const entries = files(root)
		.filter(
			(name) =>
				/\.(gs|js|html|json)$/.test(name) &&
				!path.basename(name).startsWith("."),
		)
		.map((name) => [
			name.replace(/\.gs$/, ".js"),
			digest(fs.readFileSync(path.join(root, name))),
		])
		.sort(([a], [b]) => a.localeCompare(b));
	requireThat(
		new Set(entries.map(([name]) => name)).size === entries.length,
		"Conflicting logical script names.",
	);
	return Object.fromEntries(entries);
}
function same(a: unknown, b: unknown): boolean {
	return JSON.stringify(a) === JSON.stringify(b);
}
function claspEnvironment(): NodeJS.ProcessEnv {
	// Never inherit target overrides or verbose OAuth diagnostics from the caller.
	const env = { ...process.env };
	for (const key of Object.keys(env)) {
		if (/^(clasp_config_|DEBUG$|NODE_OPTIONS$|NODE_PATH$)/.test(key))
			delete env[key];
	}
	// Expose a repo-local clasp binary even though deployment uses isolated workdirs.
	const localBin = fileURLToPath(
		new URL("../../../node_modules/.bin/", import.meta.url),
	);
	if (fs.existsSync(localBin))
		env.PATH = [env.PATH, localBin].filter(Boolean).join(path.delimiter);
	return env;
}
function projectOptions(project: string): string[] {
	return [
		"--project",
		project,
		"--ignore",
		path.join(work, "empty.claspignore"),
	];
}
function run(args: string[], cwd = work, asJSON = true): any {
	const invoke = (launcher: (typeof claspLaunchers)[number]) =>
		spawnSync(launcher.executable, [...launcher.prefix, ...args], {
			cwd,
			env: claspEnvironment(),
			input: "",
			encoding: "utf8",
			maxBuffer: 16 * 1024 * 1024,
		});
	if (!selectedClaspLauncher) {
		// Resolve the runner without executing any deployment or authentication command.
		selectedClaspLauncher = claspLaunchers.find((launcher) => {
			const probe = spawnSync(
				launcher.executable,
				[...launcher.prefix, "--version"],
				{
					cwd,
					env: claspEnvironment(),
					input: "",
					encoding: "utf8",
					maxBuffer: 16 * 1024 * 1024,
				},
			);
			return !probe.error && probe.status === 0;
		});
	}
	requireThat(
		selectedClaspLauncher,
		"No usable clasp runner: make the official @google/clasp CLI available to pnpm, npx, or PATH.",
	);
	// Once selected, never retry a real clasp command through another runner.
	const result = invoke(selectedClaspLauncher);
	if (result.error || result.status !== 0) {
		const error = new Error(
			"clasp failed; check authentication, enabled Apps Script API, permissions and CLI contract. Raw diagnostics withheld to protect credentials.",
		);
		(error as Error & { exitCode?: number }).exitCode = result.status || 1;
		throw error;
	}
	if (!asJSON) return result.stdout;
	return parseJSON(result.stdout);
}
function clasp(
	command: string,
	args: string[] = [],
	cwd = path.join(work, "project"),
): any {
	return run(
		[
			"--json",
			...projectOptions(path.join(cwd, ".clasp.json")),
			command,
			...args,
		],
		cwd,
	);
}
function clone(
	scriptId: string | undefined,
	destination: string,
	version?: number,
): Record<string, string> {
	requireThat(identifier(scriptId), "Invalid script binding.");
	fs.mkdirSync(destination);
	const retrieved = run(
		[
			"--json",
			...projectOptions(destination),
			"clone-script",
			scriptId,
			...(version === undefined ? [] : [String(version)]),
		],
		destination,
	);
	requireThat(
		Array.isArray(retrieved.files) &&
			retrieved.files.length > 0 &&
			retrieved.files.every((file) => {
				const resolved = path.resolve(destination, file);
				return (
					inside(destination, resolved) &&
					fs.existsSync(resolved) &&
					fs.statSync(resolved).isFile()
				);
			}),
		"Incomplete retrieval, including skipped empty files; cannot preserve remote project.",
	);
	requireThat(
		json(path.join(destination, ".clasp.json")).scriptId === scriptId,
		"Cloned script binding mismatch.",
	);
	requireThat(
		fs.existsSync(path.join(destination, "appsscript.json")),
		"Remote manifest missing.",
	);
	const names = files(destination);
	requireThat(
		names.every(
			(name) =>
				name === ".clasp.json" ||
				(!name.split(path.sep).some((part) => part.startsWith(".")) &&
					/\.(gs|js|html)$/.test(name)) ||
				name === "appsscript.json",
		),
		"Unexpected remote file type; cannot preserve complete project.",
	);
	return payload(destination);
}
function save(): void {
	writeJSON(path.join(work, "deployment.json"), state);
}
function isPolicy(value: unknown): value is Policy {
	if (!value || typeof value !== "object") return false;
	const candidate = value as Record<string, unknown>;
	return (
		accessValues.some((access) => access === candidate.access) &&
		executeValues.some((executeAs) => executeAs === candidate.executeAs)
	);
}
function policy(value: unknown): Policy {
	requireThat(
		isPolicy(value),
		"Cannot establish selected deployment policy. Supply an explicit access/execute-as pair or retrieve its versioned manifest.",
	);
	return { access: value.access, executeAs: value.executeAs };
}
function verifyURL(id: string, cwd: string): string {
	// The clasp JSON response may be followed by a browser instruction on stdout.
	const output = run(
		[
			"--json",
			...projectOptions(path.join(cwd, ".clasp.json")),
			"open-web-app",
			id,
		],
		cwd,
		false,
	);
	const match = output.match(
		/^\s*(\{[\s\S]*?\})\s*(?:Open [^\r\n]+ in your browser to continue\.\s*)?$/,
	);
	requireThat(match, "Unexpected open-web-app metadata response.");
	const url = new URL(parseJSON(match[1]).url);
	requireThat(
		url.protocol === "https:" &&
			!url.username &&
			!url.password &&
			url.hostname === "script.google.com" &&
			(url.pathname === `/macros/s/${id}/exec` ||
				new RegExp(`^/a/(?:macros/[^/]+|[^/]+/macros)/s/${id}/exec$`).test(
					url.pathname,
				)),
		"Metadata did not confirm a production /exec Web App entry point.",
	);
	return url.toString();
}

try {
	requireThat(
		Number(process.versions.node.split(".")[0]) >= 20,
		"Node.js >=20 is required.",
	);
	const flags = process.argv
		.slice(2)
		.filter((arg) => arg.startsWith("--"))
		.map((arg) => arg.split("=")[0]);
	requireThat(
		new Set(flags).size === flags.length,
		"Duplicate options are forbidden.",
	);
	const { values: v } = parseArgs({
		options: {
			source: { type: "string" },
			derivative: { type: "string" },
			report: { type: "string" },
			workdir: { type: "string" },
			"new-project": { type: "string" },
			"script-id": { type: "string" },
			"clasp-config": { type: "string" },
			initial: { type: "boolean" },
			additional: { type: "boolean" },
			"deployment-id": { type: "string" },
			access: { type: "string" },
			"execute-as": { type: "string" },
			"exclusive-coordination": { type: "boolean" },
			"allow-manifest-update": { type: "boolean" },
		},
	});
	requireThat(
		v.source && v.report && v.workdir,
		"Required: --source, --report, --workdir. See SKILL.md.",
	);
	requireThat(
		[v["new-project"], v["script-id"], v["clasp-config"]].filter(
			(x) => x !== undefined,
		).length === 1,
		"Select exactly one new-project, script-id or clasp-config.",
	);
	requireThat(
		[v.initial, v.additional, v["deployment-id"]].filter(Boolean).length === 1,
		"Select exactly one initial, additional or deployment-id.",
	);
	requireThat(
		!v["new-project"] || v.initial,
		"New projects require initial deployment.",
	);
	requireThat(
		!v["new-project"] || v["new-project"].trim(),
		"Project title must be non-empty.",
	);
	requireThat(
		Boolean(v.access) === Boolean(v["execute-as"]),
		"Supply access and execute-as together.",
	);
	const requestedPolicy = v.access
		? policy({ access: v.access, executeAs: v["execute-as"] })
		: undefined;
	requireThat(
		v["deployment-id"] || requestedPolicy,
		"New deployments require an explicit access and execute-as policy.",
	);
	requireThat(
		!v["deployment-id"] || identifier(v["deployment-id"]),
		"Invalid deployment ID.",
	);
	let scriptId = v["script-id"];
	if (v["clasp-config"])
		scriptId = json(fs.realpathSync(v["clasp-config"])).scriptId;
	requireThat(
		v["new-project"] || identifier(scriptId),
		"Invalid script binding.",
	);
	requireThat(
		v["new-project"] || v["exclusive-coordination"],
		"Existing projects require --exclusive-coordination; clasp has no atomic compare-and-swap.",
	);
	const source = readArtifact(v.source);
	const artifact = v.derivative ? readArtifact(v.derivative) : source;
	if (v.derivative) {
		const originalStat = fs.statSync(source.path);
		const derivativeStat = fs.statSync(artifact.path);
		requireThat(
			originalStat.dev !== derivativeStat.dev ||
				originalStat.ino !== derivativeStat.ino,
			"Source and derivative alias the same file.",
		);
	}
	const reportPath = fs.realpathSync(v.report);
	const report = json(reportPath);
	requireThat(
		["compatible", "convertible"].includes(report.decision),
		"Compatibility decision is unsupported or uncertain.",
	);
	requireThat(
		report.sourceSha256 === source.sha256 &&
			report.artifactSha256 === artifact.sha256,
		"Compatibility report hashes do not match artifacts.",
	);
	requireThat(
		report.secretReview === "passed",
		"Resolve security concerns before deployment.",
	);
	for (const key of [
		"evidence",
		"dependencies",
		"transformations",
		"limitations",
		"unresolved",
	])
		requireThat(
			Array.isArray(report[key]) &&
				report[key].every((value) => typeof value === "string"),
			`Report requires ${key} array.`,
		);
	requireThat(
		report.unresolved.length === 0,
		"Resolve dependencies before deployment.",
	);
	requireThat(
		report.evidence.length > 0,
		"Report requires assessment evidence.",
	);
	requireThat(
		report.decision === "convertible"
			? v.derivative &&
					artifact.path !== source.path &&
					report.transformations.length > 0
			: !v.derivative && report.transformations.length === 0,
		"Compatible input must be unchanged; convertible input requires a separate reported derivative.",
	);
	const destination = path.resolve(v.workdir);
	// A fresh directory is mandatory: do not overwrite state after a partial run.
	const parent = fs.realpathSync(path.dirname(destination));
	work = path.join(parent, path.basename(destination));
	requireThat(
		!fs.existsSync(work),
		"Workdir must not exist. Resume explicitly using recorded IDs in a fresh workdir.",
	);
	requireThat(
		![source.path, artifact.path, reportPath].some((file) =>
			inside(work, file),
		),
		"Source/report/output aliases are forbidden.",
	);
	stage = "prerequisite check";
	const help = run(["--help"], parent, false);
	const commands = [
		"create-script",
		"clone-script",
		"push",
		"create-version",
		"create-deployment",
		"update-deployment",
		"list-deployments",
		"open-web-app",
		"show-authorized-user",
	];
	requireThat(
		commands.every((command) => help.includes(command)) &&
			help.includes("--json") &&
			help.includes("--project") &&
			help.includes("--ignore"),
		"Required clasp commands/JSON output unavailable.",
	);
	for (const [command, flags] of [
		["push", ["--force"]],
		["create-deployment", ["--versionNumber"]],
		["update-deployment", ["--versionNumber"]],
		["create-script", ["--type", "--title"]],
	] as Array<[string, string[]]>) {
		const commandHelp = run([command, "--help"], parent, false);
		requireThat(
			flags.every((flag) => commandHelp.includes(flag)),
			`Missing ${command} capabilities.`,
		);
	}
	requireThat(
		run(["--json", "show-authorized-user"], parent).loggedIn === true,
		"Authenticate interactively with clasp login before deployment; enable Apps Script API.",
	);
	fs.mkdirSync(work, { mode: 0o700 });
	fs.writeFileSync(path.join(work, "empty.claspignore"), "");
	writeJSON(path.join(work, "compatibility.json"), report);
	state = {
		scriptId,
		deploymentId: v["deployment-id"],
		source: { path: source.path, sha256: source.sha256 },
		artifact: { path: artifact.path, sha256: artifact.sha256 },
		report: "compatibility.json",
		runtimeSmokeTest: "not performed",
		stage: "prepared",
	};
	save();
	const project = path.join(work, "project");
	let baseline;
	let deployments: Array<{ deploymentId: string; versionNumber: number }> = [];
	let selected;
	let chosenPolicy = requestedPolicy;
	if (!v["new-project"]) {
		stage = "retrieve existing project";
		baseline = clone(scriptId, project);
		deployments = clasp("list-deployments");
		requireThat(Array.isArray(deployments), "Unexpected deployment list.");
		selected = deployments.find((d) => d.deploymentId === v["deployment-id"]);
		if (v["deployment-id"]) {
			requireThat(
				selected &&
					Number.isInteger(selected.versionNumber) &&
					selected.versionNumber > 0,
				"Selected deployment is invalid or unversioned; no replacement will be created.",
			);
			state.previousURL = verifyURL(selected.deploymentId, project);
			const versioned = path.join(work, "selected-version");
			clone(scriptId, versioned, selected.versionNumber);
			const deployedPolicy = json(
				path.join(versioned, "appsscript.json"),
			).webapp;
			const previousPolicy = isPolicy(deployedPolicy)
				? policy(deployedPolicy)
				: undefined;
			requireThat(
				previousPolicy || (requestedPolicy && v["allow-manifest-update"]),
				"Cannot establish deployed policy; supply explicit policy and --allow-manifest-update before changing production.",
			);
			requireThat(
				!requestedPolicy ||
					same(previousPolicy, requestedPolicy) ||
					v["allow-manifest-update"],
				"Production policy change requires --allow-manifest-update, even when remote HEAD already has the requested policy.",
			);
			state.previousPolicy = previousPolicy || null;
			chosenPolicy = requestedPolicy || previousPolicy;
		}
		requireThat(
			!v.initial || deployments.filter((d) => d.versionNumber > 0).length === 0,
			"Versioned deployments already exist; select deployment-id or explicitly additional.",
		);
		// Only a byte-identical minimal wrapper establishes doGet ownership.
		const wrapper = fs.readFileSync(path.join(templates, "Code.gs"));
		const projectFiles = files(project);
		const codeNames = projectFiles.filter((name) => /\.(gs|js)$/.test(name));
		const own = codeNames.filter(
			(name) =>
				[
					"Code.gs",
					"Code.js",
					"GasHtmlArtifact.gs",
					"GasHtmlArtifact.js",
				].includes(name) &&
				fs.readFileSync(path.join(project, name)).equals(wrapper),
		);
		requireThat(
			codeNames.every(
				(name) =>
					own.includes(name) ||
					!/\bdoGet\b/.test(fs.readFileSync(path.join(project, name), "utf8")),
			),
			"Conflicting doGet ownership; reconcile manually before deployment.",
		);
		const indexNames = projectFiles.filter(
			(name) => path.basename(name).toLowerCase() === "index.html",
		);
		requireThat(
			indexNames.length === 0 ||
				(indexNames.length === 1 &&
					indexNames[0] === "Index.html" &&
					own.length === 1),
			"Conflicting Index ownership; reconcile manually.",
		);
		requireThat(own.length <= 1, "Ambiguous wrapper ownership.");
		if (!own.length) {
			const wrapperName = codeNames.some((name) =>
				["Code.gs", "Code.js"].includes(name),
			)
				? "GasHtmlArtifact.gs"
				: "Code.gs";
			requireThat(
				!codeNames.some((name) => name.replace(/\.js$/, ".gs") === wrapperName),
				"Wrapper file belongs to another application.",
			);
			fs.copyFileSync(
				path.join(templates, "Code.gs"),
				path.join(project, wrapperName),
			);
		}
	} else {
		fs.mkdirSync(project);
		fs.copyFileSync(
			path.join(templates, "Code.gs"),
			path.join(project, "Code.gs"),
		);
		fs.copyFileSync(
			path.join(templates, "appsscript.json"),
			path.join(project, "appsscript.json"),
		);
	}
	fs.writeFileSync(path.join(project, "Index.html"), artifact.bytes);
	requireThat(
		fs.readFileSync(path.join(project, "Index.html")).equals(artifact.bytes),
		"Artifact bytes changed.",
	);
	const manifestPath = path.join(project, "appsscript.json");
	const originalManifest = fs.readFileSync(manifestPath);
	const manifest = json(manifestPath);
	requireThat(
		manifest && typeof manifest === "object" && !Array.isArray(manifest),
		"Invalid manifest.",
	);
	const manifestChanged = !same(
		manifest.webapp && policy(manifest.webapp),
		chosenPolicy,
	);
	if (manifestChanged) {
		requireThat(
			v["allow-manifest-update"],
			"Manifest policy change requires --allow-manifest-update after reviewing chosen policy; no automatic force overwrite.",
		);
		manifest.webapp = { ...manifest.webapp, ...chosenPolicy };
		writeJSON(manifestPath, manifest);
	}
	state.policy = chosenPolicy;
	state.files = files(project).filter((name) => name !== ".clasp.json");
	const expectedPayload = payload(project);
	state.payloadSha256 = expectedPayload;
	console.log(`Push payload: ${state.files.join(", ")}`);
	console.log(
		`Web App policy: ${JSON.stringify(chosenPolicy)}; manifest update: ${manifestChanged}`,
	);
	save();
	if (v["new-project"]) {
		// Create in isolated bootstrap: clasp creation pulls defaults, never overwrite prepared files.
		stage = "create project";
		state.stage = "project creation attempted";
		save();
		const bootstrap = path.join(work, "bootstrap");
		fs.mkdirSync(bootstrap);
		// Stream the official creation message: JSON emits the ID too late if pull fails.
		await new Promise<void>((resolve, reject) => {
			requireThat(selectedClaspLauncher, "clasp runner was not initialized.");
			const child = spawn(
				selectedClaspLauncher.executable,
				[
					...selectedClaspLauncher.prefix,
					...projectOptions(bootstrap),
					"create-script",
					"--type",
					"standalone",
					"--title",
					v["new-project"]!,
				],
				{
					cwd: bootstrap,
					env: claspEnvironment(),
					stdio: ["ignore", "pipe", "pipe"] as const,
				},
			);
			let output = "";
			child.stdout.on("data", (bytes) => {
				output += bytes.toString();
				const match = output.match(
					/Created new script: https:\/\/script\.google\.com\/d\/([A-Za-z0-9_-]+)\/edit/,
				);
				if (match && !state.scriptId) {
					scriptId = match[1];
					state.scriptId = scriptId;
					state.stage = "project created";
					save();
				}
			});
			child.stderr.resume(); // Never reproduce credential-bearing diagnostics.
			child.on("error", reject);
			child.on("close", (code) => {
				if (code !== 0) {
					const error = new Error(
						"Project creation/pull failed; inspect recorded ID or bootstrap binding. Do not repeat creation.",
					);
					(error as Error & { exitCode?: number }).exitCode = code || 1;
					reject(error);
				} else resolve();
			});
		});
		requireThat(
			identifier(scriptId),
			"Creation ID unavailable; inspect bootstrap binding before resuming.",
		);
		writeJSON(path.join(project, ".clasp.json"), { scriptId, rootDir: "." });
	} else {
		stage = "remote change check";
		const fresh = clone(scriptId, path.join(work, "remote-check"));
		requireThat(
			same(baseline, fresh),
			"Remote project changed since retrieval; nothing pushed. Restart under exclusive coordination.",
		);
		requireThat(
			same(deployments, clasp("list-deployments")),
			"Deployment metadata changed since retrieval; nothing pushed.",
		);
		writeJSON(path.join(project, ".clasp.json"), { scriptId, rootDir: "." });
	}
	stage = "push";
	state.stage = "push attempted";
	save();
	pushAttempted = true;
	// Force only the caller-authorized policy change, with all unrelated fields preserved.
	clasp("push", manifestChanged ? ["--force"] : []);
	pushed = true;
	state.stage = "remote HEAD pushed";
	save();
	const readback = clone(scriptId, path.join(work, "push-readback"));
	requireThat(
		same(expectedPayload, readback),
		"Push readback differs from prepared complete payload; production deployment not advanced.",
	);
	requireThat(
		manifestChanged || fs.readFileSync(manifestPath).equals(originalManifest),
		"Unrequested manifest modification.",
	);
	stage = "create version";
	const version = clasp("create-version", ["gas-html-artifact"]);
	requireThat(
		Number.isInteger(version.versionNumber) && version.versionNumber > 0,
		"Invalid version metadata.",
	);
	state.version = version.versionNumber;
	state.stage = "version created";
	save();
	stage = "verify immutable version";
	const versioned = path.join(work, "deployed-version");
	const versionPayload = clone(scriptId, versioned, state.version);
	requireThat(
		same(expectedPayload, versionPayload),
		"Immutable version differs from prepared payload; production deployment not advanced.",
	);
	stage = "deploy";
	state.stage = "deployment attempted";
	save();
	deploymentAttempted = true;
	const result = selected
		? clasp("update-deployment", [
				selected.deploymentId,
				"--versionNumber",
				String(state.version),
			])
		: clasp("create-deployment", [
				"--versionNumber",
				String(state.version),
				"--description",
				"gas-html-artifact",
			]);
	requireThat(
		identifier(result.deploymentId),
		"Deployment did not return ID; inspect list-deployments before retrying.",
	);
	state.deploymentId = result.deploymentId;
	state.stage = "deployment returned";
	save();
	requireThat(
		!selected || result.deploymentId === selected.deploymentId,
		"Updated deployment ID changed.",
	);
	stage = "verify deployment";
	const live = clasp("list-deployments").find(
		(d) => d.deploymentId === state.deploymentId,
	);
	requireThat(
		live && live.versionNumber === state.version,
		"Deployment readback version mismatch.",
	);
	requireThat(
		same(
			policy(json(path.join(versioned, "appsscript.json")).webapp),
			chosenPolicy,
		),
		"Deployed policy mismatch.",
	);
	requireThat(identifier(state.deploymentId), "Invalid deployed ID.");
	state.url = verifyURL(state.deploymentId, project);
	requireThat(
		!state.previousURL || state.previousURL === state.url,
		"Production URL changed during update.",
	);
	state.stage = "verified";
	save();
	console.log(JSON.stringify(state, null, 2));
} catch (error) {
	console.error(
		`Failed stage: ${stage}. ${error instanceof Error ? error.message : "Unknown error"}`,
	);
	if (pushed)
		console.error(
			deploymentAttempted
				? "Remote HEAD changed and deployment may have advanced; verification incomplete. Inspect recorded IDs before resuming."
				: "Remote HEAD changed; selected production deployment was not advanced. No rollback performed.",
		);
	else if (pushAttempted)
		console.error(
			"Push outcome uncertain; inspect remote HEAD before resuming. No later stage was attempted.",
		);
	if (state) {
		state.failedStage = stage;
		try {
			save();
		} catch {
			/* Retain the previous record on filesystem failure. */
		}
	}
	if (state)
		console.error(
			`Inspect ${path.join(work, "deployment.json")} and staging files; never repeat creation blindly.`,
		);
	process.exitCode = (error as Error & { exitCode?: number }).exitCode || 1;
}
