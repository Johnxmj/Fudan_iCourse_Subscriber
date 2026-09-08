# Fudan iCourse Edge Live Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Manifest V3 Microsoft Edge extension that uses the browser's official WebVPN login state to discover and play currently live iCourse sessions, and exposes an extension-owned player frame to the approved GitHub Pages origin.

**Architecture:** Pure mapping and protocol code is tested as ES modules. A background service worker owns session probes and approved external messages; an extension-origin player page owns HLS.js, media bytes, signed URLs, and `MediaSource`. The popup and GitHub Pages send only safe course/view commands.

**Tech Stack:** Microsoft Edge Manifest V3, JavaScript ES2020, HLS.js 1.5.18 from the local-player vendor directory, `chrome.runtime`, `chrome.tabs`, `chrome.cookies`, `chrome.scripting`, `node:test`.

## Global Constraints

- The extension never stores or requests the UIS password.
- Use only the browser's existing official CAS/WebVPN session.
- Support only sessions the platform currently marks live.
- Do not expose signed upstream media URLs to GitHub Pages, popup state, logs, or extension storage.
- Do not download, record, archive, or redistribute media.
- Restrict host permissions to Fudan WebVPN/iCourse and the project's GitHub Pages origin.
- Keep the extension unpacked-install ZIP reproducible from the public repository.
- Complete the extension-origin cookie/media proof before building the full UI.

---

## File Map

- `edge_extension/manifest.json`: permissions, background worker, popup, and web-accessible player frame.
- `edge_extension/src/protocol.js`: versioned safe message schema.
- `edge_extension/src/webvpn-url.js`: deterministic iCourse-to-WebVPN URL conversion.
- `edge_extension/src/live-api.js`: current-live course mapping and source refresh.
- `edge_extension/src/background.js`: session probe, CAS tab, internal/external messaging.
- `edge_extension/player/index.html`: extension-origin player frame.
- `edge_extension/player/player.js`: HLS lifecycle and WebVPN request loader.
- `edge_extension/player/player.css`: embedded/full-page player styling.
- `edge_extension/popup/index.html`: quick launcher.
- `edge_extension/popup/popup.js`: course list and launch actions.
- `edge_extension/scripts/build.mjs`: deterministic distribution assembly.
- `tests/extension/`: Node protocol, URL, mapping, permission, and packaging tests.

### Task 1: Versioned message protocol and safe payloads

**Files:**
- Create: `edge_extension/src/protocol.js`
- Create: `tests/extension/protocol.test.mjs`

**Interfaces:**
- Produces: `PROTOCOL_VERSION`, `parseRequest(value)`, `safeCourse(course)`, and response types `CAPABILITIES`, `LIST_LIVE`, `OPEN_PLAYER`, `SET_VIEW`, `REFRESH`, `LOGIN_REQUIRED`, and `ERROR`.

- [ ] **Step 1: Write failing protocol tests**

```javascript
import test from "node:test";
import assert from "node:assert/strict";
import { parseRequest, safeCourse } from "../../edge_extension/src/protocol.js";

test("rejects messages with a different protocol version", () => {
  assert.throws(() => parseRequest({ version: 2, type: "LIST_LIVE" }), /protocol version/);
});

test("safe course payload omits every source field", () => {
  const safe = safeCourse({ course_id: "1", sub_id: "2", course_title: "Analysis", live_url: { output: "secret" } });
  assert.deepEqual(Object.keys(safe).sort(), ["available_views", "course_id", "course_title", "ends_at", "room", "starts_at", "status", "sub_id", "sub_title", "teacher"]);
  assert.equal(JSON.stringify(safe).includes("secret"), false);
});
```

- [ ] **Step 2: Run and verify RED**

Run: `node --test tests/extension/protocol.test.mjs`

Expected: module-not-found failure.

- [ ] **Step 3: Implement strict parsing and whitelisted serialization**

```javascript
export const PROTOCOL_VERSION = 1;
const TYPES = new Set(["CAPABILITIES", "LIST_LIVE", "OPEN_PLAYER", "SET_VIEW", "REFRESH"]);

export function parseRequest(value) {
  if (!value || value.version !== PROTOCOL_VERSION) throw new TypeError("unsupported protocol version");
  if (!TYPES.has(value.type)) throw new TypeError("unsupported message type");
  return { version: PROTOCOL_VERSION, type: value.type, payload: value.payload || {} };
}

export function safeCourse(course) {
  const keys = ["course_id", "course_title", "teacher", "room", "sub_id", "sub_title", "starts_at", "ends_at", "status", "available_views"];
  return Object.fromEntries(keys.map((key) => [key, course[key] ?? (key === "available_views" ? [] : "")]));
}
```

- [ ] **Step 4: Run and verify GREEN**

Run: `node --test tests/extension/protocol.test.mjs`

Expected: 2 tests pass.

- [ ] **Step 5: Commit the protocol**

```bash
git add -f edge_extension/src/protocol.js tests/extension/protocol.test.mjs
git commit -m "feat: define safe live extension protocol"
```

### Task 2: iCourse WebVPN URL and live-response adapters

**Files:**
- Create: `edge_extension/src/webvpn-url.js`
- Create: `edge_extension/src/live-api.js`
- Create: `tests/extension/webvpn-url.test.mjs`
- Create: `tests/extension/live-api.test.mjs`

**Interfaces:**
- Produces: `toWebVpnUrl(url)`, `mapLiveCourse(courseDetail, subInfo)`, `listLiveCourses(fetcher, courseIds)`, and `resolveLiveSource(fetcher, courseId, subId, view)`.

- [ ] **Step 1: Write parity and current-live tests**

Use the same invented host fixtures as the Python tests and one public deterministic assertion generated by `src.api.webvpn.get_vpn_url("https://icourse.fudan.edu.cn/path?q=1")`. Assert that JavaScript and Python output match exactly, without including an authenticated URL.

```javascript
test("ended lectures are not mapped as live", () => {
  assert.equal(mapLiveCourse({ title: "Analysis" }, { sub_status: 2, sub_id: "2", live_url: {} }), null);
});

test("source resolution accepts only known views", async () => {
  await assert.rejects(() => resolveLiveSource(fakeFetcher, "1", "2", "recording"), /unknown live view/);
});
```

- [ ] **Step 2: Run and verify RED**

Run: `node --test tests/extension/webvpn-url.test.mjs tests/extension/live-api.test.mjs`

Expected: module-not-found failures.

- [ ] **Step 3: Implement the fixed iCourse WebVPN base and adapters**

Use the repository's public WebVPN AES key/IV algorithm to calculate the host component during build, then export a fixed prefix for `https://icourse.fudan.edu.cn`. `toWebVpnUrl()` must reject any hostname other than `icourse.fudan.edu.cn`; extension code does not become a generic proxy.

```javascript
const VIEW_PATHS = {
  teacher: ["output", "m3u8"],
  student: ["output_student", "m3u8"],
  teacher_audio: ["output", "m3u8_audio"],
  student_audio: ["output_student", "m3u8_audio"],
};

export async function resolveLiveSource(fetcher, courseId, subId, view) {
  if (!VIEW_PATHS[view]) throw new TypeError("unknown live view");
  const info = await fetcher.getSubInfo(courseId, subId);
  if (Number(info.sub_status) !== 1) throw new Error("lecture is not currently live");
  const value = VIEW_PATHS[view].reduce((node, key) => node && node[key], info.live_url);
  if (typeof value !== "string") throw new Error("live view unavailable");
  return toWebVpnUrl(value);
}
```

- [ ] **Step 4: Run adapter tests**

Run: `node --test tests/extension/webvpn-url.test.mjs tests/extension/live-api.test.mjs`

Expected: all tests pass.

- [ ] **Step 5: Commit the adapters**

```bash
git add -f edge_extension/src tests/extension
git commit -m "feat: adapt current live sources in Edge"
```

### Task 3: Manifest, cookie, and MediaSource proof of transport

**Files:**
- Create: `edge_extension/manifest.json`
- Create: `edge_extension/src/background.js`
- Create: `edge_extension/player/index.html`
- Create: `edge_extension/player/player.js`
- Create: `edge_extension/player/player.css`
- Create: `tests/extension/manifest.test.mjs`
- Create: `tests/extension/player.test.mjs`

**Interfaces:**
- Produces: an extension page that can fetch a WebVPN-wrapped live manifest using browser cookies, rewrite segment requests, open a `MediaSource`, and render a live frame.

- [ ] **Step 1: Write failing manifest-permission tests**

```javascript
test("manifest grants only required Fudan and Pages origins", () => {
  const manifest = JSON.parse(readFileSync("edge_extension/manifest.json", "utf8"));
  assert.deepEqual(manifest.host_permissions.sort(), [
    "https://icourse.fudan.edu.cn/*",
    "https://webvpn.fudan.edu.cn/*",
  ]);
  assert.deepEqual(manifest.externally_connectable.matches, ["https://johnxmj.github.io/*"]);
  assert.equal(manifest.permissions.includes("downloads"), false);
});
```

- [ ] **Step 2: Run and verify RED**

Run: `node --test tests/extension/manifest.test.mjs tests/extension/player.test.mjs`

Expected: missing manifest/player failures.

- [ ] **Step 3: Implement the minimal extension-origin player**

Create a Manifest V3 extension with permissions `cookies`, `tabs`, `scripting`, and `storage`; no `downloads`, broad `<all_urls>`, or password storage. Make `player/index.html` a web-accessible resource only for `https://johnxmj.github.io/*`. Copy the pinned HLS.js distribution from `live_player/web/vendor/` during the build.

Include a stable public manifest `key` so unpacked builds have one deterministic extension ID. Record that expected ID in the manifest test and Pages configuration; the key is public identity metadata, not a credential.

```json
{
  "manifest_version": 3,
  "name": "Fudan iCourse Live Player",
  "version": "0.1.0",
  "permissions": ["cookies", "tabs", "scripting", "storage"],
  "host_permissions": ["https://webvpn.fudan.edu.cn/*", "https://icourse.fudan.edu.cn/*"],
  "background": {"service_worker": "src/background.js", "type": "module"},
  "action": {"default_popup": "popup/index.html"},
  "externally_connectable": {"matches": ["https://johnxmj.github.io/*"]},
  "web_accessible_resources": [{"resources": ["player/*"], "matches": ["https://johnxmj.github.io/*"]}]
}
```

The player accepts `{courseId, subId, view}` only after an internal extension handshake. It asks the background worker for a fresh source, constructs HLS.js with a custom loader that rewrites direct iCourse fragment URLs through `toWebVpnUrl()`, and keeps the source string in closure scope rather than DOM attributes or messages to Pages.

- [ ] **Step 4: Add a manual proof script and execute it in Edge**

Load the unpacked extension, complete official CAS login, open the extension player for an authorized current-live session, and record only these safe assertions in the task notes:

```text
manifest HTTP status: 200
fragment count after 15 seconds: >= 1
MediaSource readyState: open
video readyState: >= 2
videoWidth: > 0
currentTime advances over 5 seconds: true
```

If cookies are not included from the extension page, stop this task and change the player transport to a Fudan-origin content-script relay before any popup or Pages work. The acceptance values above remain unchanged.

- [ ] **Step 5: Run automated tests and commit the proven transport**

Run: `node --test tests/extension/*.test.mjs`

Expected: all tests pass.

```bash
git add -f edge_extension tests/extension
git commit -m "feat: prove Edge live media transport"
```

### Task 4: Background session state and official login flow

**Files:**
- Modify: `edge_extension/src/background.js`
- Create: `tests/extension/background.test.mjs`

**Interfaces:**
- Produces: `probeSession()`, `openCasLogin()`, and internal handlers for `CAPABILITIES`, `LIST_LIVE`, `OPEN_PLAYER`, `SET_VIEW`, and `REFRESH`.

- [ ] **Step 1: Write failing session-transition tests**

```javascript
test("cold WebVPN session becomes login-required without password retries", async () => {
  const state = await probeSession({ fetchJson: async () => ({ httpStatus: 302, location: "/login" }) });
  assert.deepEqual(state, { state: "login-required" });
});

test("login action opens the official CAS page", async () => {
  const opened = [];
  await openCasLogin({ tabsCreate: (value) => opened.push(value) });
  assert.equal(new URL(opened[0].url).hostname, "webvpn.fudan.edu.cn");
});
```

- [ ] **Step 2: Run and verify RED**

Run: `node --test tests/extension/background.test.mjs`

Expected: missing exported functions.

- [ ] **Step 3: Implement the explicit state machine**

Use states `unknown`, `ready`, `login-required`, and `failed`. Probe a harmless authenticated iCourse user-info endpoint through WebVPN. A cold session returns `LOGIN_REQUIRED`; only a user-initiated action opens the official CAS page. Do not automate password submission. After the CAS tab reaches the iCourse service, close only the extension-created login tab and refresh live courses.

```javascript
export async function probeSession(deps) {
  try {
    const result = await deps.fetchJson();
    if (result.httpStatus === 302 || result.location === "/login") return { state: "login-required" };
    if (result.httpStatus === 200 && [0, 200].includes(result.body?.code)) return { state: "ready" };
    return { state: "failed" };
  } catch (_) {
    return { state: "failed" };
  }
}
```

- [ ] **Step 4: Run tests and commit**

Run: `node --test tests/extension/*.test.mjs`

Expected: all extension tests pass.

```bash
git add -f edge_extension/src/background.js tests/extension/background.test.mjs
git commit -m "feat: manage Edge WebVPN login state"
```

### Task 5: Popup and extension-owned embedded player

**Files:**
- Create: `edge_extension/popup/index.html`
- Create: `edge_extension/popup/popup.css`
- Create: `edge_extension/popup/popup.js`
- Modify: `edge_extension/player/index.html`
- Modify: `edge_extension/player/player.js`
- Create: `tests/extension/popup.test.mjs`
- Create: `tests/extension/external.test.mjs`

**Interfaces:**
- Produces: a popup current-live list and an externally connectable, extension-origin player frame for the approved Pages site.

- [ ] **Step 1: Write failing popup and origin-authorization tests**

```javascript
test("external messages reject unapproved origins", async () => {
  const response = await handleExternal({ version: 1, type: "CAPABILITIES" }, { url: "https://evil.invalid/" });
  assert.equal(response.error.code, "ORIGIN_DENIED");
});

test("popup sorts live courses by start time", () => {
  assert.deepEqual(sortLiveCourses([{ starts_at: "10:00", sub_id: "2" }, { starts_at: "08:00", sub_id: "1" }]).map(x => x.sub_id), ["1", "2"]);
});
```

- [ ] **Step 2: Run and verify RED**

Run: `node --test tests/extension/popup.test.mjs tests/extension/external.test.mjs`

Expected: missing exports.

- [ ] **Step 3: Implement safe popup and external handshake**

The popup displays live course name, teacher, room, and start time; its primary action opens the extension player in a normal Edge tab. The external API accepts only the exact Pages origin and only `CAPABILITIES`, `LIST_LIVE`, and `OPEN_PLAYER`. `OPEN_PLAYER` creates or focuses the extension-owned player frame/tab and passes only IDs and the selected view.

The Pages embedding handshake uses a random nonce generated by the extension frame. The frame sends `{type: "LIVE_PLAYER_READY", nonce}` to the exact parent origin, and all subsequent commands must echo the nonce and protocol version.

```javascript
export async function handleExternal(message, sender, deps) {
  const origin = new URL(sender.url).origin;
  if (origin !== "https://johnxmj.github.io") {
    return { error: { code: "ORIGIN_DENIED", message: "origin is not allowed" } };
  }
  const request = parseRequest(message);
  if (request.type === "CAPABILITIES") return { version: 1, playerFrame: deps.playerFrameUrl };
  if (request.type === "LIST_LIVE") return { version: 1, courses: (await deps.listLive()).map(safeCourse) };
  if (request.type === "OPEN_PLAYER") return deps.openPlayer(request.payload);
  return { error: { code: "UNSUPPORTED", message: "request is not externally available" } };
}
```

- [ ] **Step 4: Run tests and commit**

Run: `node --test tests/extension/*.test.mjs`

Expected: all extension tests pass.

```bash
git add -f edge_extension tests/extension
git commit -m "feat: add Edge live launcher and embedded player"
```

### Task 6: Deterministic extension build and smoke verification

**Files:**
- Create: `edge_extension/scripts/build.mjs`
- Create: `tests/extension/build.test.mjs`
- Modify: `README.md`

**Interfaces:**
- Produces: `dist/edge-extension/` and `dist/fudan-icourse-live-edge.zip`.

- [ ] **Step 1: Write failing package-content tests**

```javascript
test("build contains player assets and no private files", () => {
  const files = buildExtension({ output: tempDir });
  assert.equal(files.includes("player/vendor/hls.min.js"), true);
  assert.equal(files.some((file) => /\.env|cookie|credential/i.test(file)), false);
});
```

- [ ] **Step 2: Run and verify RED**

Run: `node --test tests/extension/build.test.mjs`

Expected: `buildExtension` is missing.

- [ ] **Step 3: Implement reproducible assembly**

Copy an allowlist of manifest, source, popup, player, HLS.js, and license files into `dist/edge-extension`; normalize ZIP entry timestamps to `1980-01-01T00:00:00Z`; sort entries lexically; and reject unexpected files. Keep `dist/` ignored.

```javascript
const ALLOWED_ROOTS = new Set(["manifest.json", "src", "popup", "player"]);
export function assertAllowed(relativePath) {
  const root = relativePath.split(/[\\/]/, 1)[0];
  if (!ALLOWED_ROOTS.has(root) || /(?:^|[\\/])(?:\.env|data|_run_logs)(?:[\\/]|$)/i.test(relativePath)) {
    throw new Error(`private or unexpected build input: ${relativePath}`);
  }
}
```

- [ ] **Step 4: Document developer-mode Edge installation**

Add steps for `edge://extensions`, Developer mode, Load unpacked, official CAS login, and removing the extension. State that the extension does not store a password and supports only current live sessions.

- [ ] **Step 5: Run complete extension verification**

Run:

```bash
node --test tests/extension/*.test.mjs
node edge_extension/scripts/build.mjs
git diff --check
```

Expected: all tests pass, both distribution paths exist, and `git diff --check` has no output.

- [ ] **Step 6: Commit the extension slice**

```bash
git add -f edge_extension tests/extension README.md
git commit -m "feat: package Edge current-live extension"
```
