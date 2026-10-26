// Managed by gas-drive-html-server. Edit the Drive files, not this renderer.
const ROOT_FOLDER_ID = "__ROOT_FOLDER_ID__";

function isDriveId_(value) {
	return typeof value === "string" && /^[A-Za-z0-9_-]{10,}$/.test(value);
}

// Only serve objects whose parent chain reaches the configured root. No shortcuts.
function isWithinRoot_(item) {
	const pending = [item];
	const visited = new Set();
	while (pending.length) {
		const current = pending.pop();
		const id = current.getId();
		if (id === ROOT_FOLDER_ID) return true;
		if (visited.has(id)) continue;
		visited.add(id);
		if (visited.size > 200) return false;
		const parents = current.getParents();
		while (parents.hasNext()) pending.push(parents.next());
	}
	return false;
}

function isHtml_(file) {
	return /\.html?$/i.test(file.getName()) && file.getMimeType() === "text/html";
}

function listDirectory_(folder) {
	const rows = [];
	const folders = folder.getFolders();
	while (folders.hasNext()) {
		const child = folders.next();
		rows.push({
			id: child.getId(),
			name: child.getName(),
			directory: true,
			updated: child.getLastUpdated().toISOString(),
			size: "",
		});
	}
	const files = folder.getFiles();
	while (files.hasNext()) {
		const file = files.next();
		if (!isHtml_(file)) continue;
		rows.push({
			id: file.getId(),
			name: file.getName(),
			directory: false,
			updated: file.getLastUpdated().toISOString(),
			size: String(file.getSize()),
		});
	}
	return rows.sort(
		(a, b) =>
			Number(b.directory) - Number(a.directory) ||
			a.name.localeCompare(b.name) ||
			a.id.localeCompare(b.id),
	);
}

function errorPage_() {
	// HTML Service cannot set an HTTP 403/404 status code.
	return HtmlService.createHtmlOutput("<p>Page unavailable.</p>").setTitle(
		"Page unavailable",
	);
}

function doGet(e) {
	try {
		const p = (e && e.parameter) || {};
		if (
			(p.file !== undefined && p.dir !== undefined) ||
			Object.keys(p).some((k) => k !== "file" && k !== "dir")
		) {
			return errorPage_();
		}
		// Reject duplicate selectors (e.parameter retains only one occurrence).
		if (
			e &&
			e.parameters &&
			["file", "dir"].some((k) => (e.parameters[k] || []).length > 1)
		) {
			return errorPage_();
		}
		const root = DriveApp.getFolderById(ROOT_FOLDER_ID);
		if (p.file !== undefined) {
			if (!isDriveId_(p.file)) return errorPage_();
			const file = DriveApp.getFileById(p.file);
			if (!isHtml_(file) || !isWithinRoot_(file)) return errorPage_();
			return HtmlService.createHtmlOutput(
				file.getBlob().getDataAsString("UTF-8"),
			).setTitle(file.getName());
		}
		if (p.dir !== undefined && !isDriveId_(p.dir)) return errorPage_();
		const folder = p.dir ? DriveApp.getFolderById(p.dir) : root;
		if (!isWithinRoot_(folder)) return errorPage_();
		const baseUrl = ScriptApp.getService().getUrl();
		if (!/^https:\/\/script\.google\.com\//.test(baseUrl)) return errorPage_();
		const template = HtmlService.createTemplateFromFile("Index");
		template.title = "Index of /" + folder.getName() + "/";
		template.entries = listDirectory_(folder).map((row) => ({
			...row,
			url:
				baseUrl +
				"?" +
				(row.directory ? "dir" : "file") +
				"=" +
				encodeURIComponent(row.id),
		}));
		template.homeUrl = baseUrl;
		return template.evaluate().setTitle(template.title);
	} catch (_) {
		// Never disclose private file names, IDs, or Drive exceptions in errors.
		return errorPage_();
	}
}
