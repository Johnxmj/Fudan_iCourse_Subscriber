# Fudan iCourse Live Pages and Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the shared current-live interface on GitHub Pages, connect it safely to the Edge extension or an explicitly launched local bridge, and automate public Windows/extension release artifacts.

**Architecture:** `frontend/live/` is a static transport-neutral shell. It embeds an extension-origin player when the approved Edge extension is present; otherwise it accepts an explicit fragment-only pairing handoff from the local launcher. GitHub Actions deploys the existing frontend plus the live route and builds versioned artifacts without credentials or live media.

**Tech Stack:** Existing static frontend, JavaScript ES2020, CSS, Edge extension external messaging, loopback HTTP API, GitHub Pages, GitHub Actions, Python 3.12, PyInstaller, Node.js `node:test`, Python `unittest`.

## Global Constraints

- No cloud authentication or media proxy is deployed.
- GitHub Pages never receives or stores a UIS password, WebVPN cookie, signed media URL, or media bytes.
- Pages works only with the Edge extension or a user-started local bridge.
- Pairing data from the local launcher is carried in the URL fragment, never the query string.
- Current-live playback only; no recording, download, pre-release playback, or archival.
- Preserve the existing encrypted-summary frontend and its deployment path.
- Public release artifacts are reproducible and contain no `.env`, database, logs, credentials, or cookies.

---

## File Map

- `frontend/live/index.html`: Pages live route and transport-neutral player shell.
- `frontend/live/app.css`: responsive live-console presentation.
- `frontend/live/app.js`: capability detection and safe UI state.
- `frontend/live/transports/extension.js`: extension handshake and embedded frame.
- `frontend/live/transports/local.js`: fragment-only local bridge pairing.
- `frontend/live/vendor/hls.min.js`: build-synchronized player asset for local fallback.
- `frontend/index.html`: link to the live route without changing existing summary behavior.
- `scripts/sync_live_web.mjs`: copy/check shared static assets deterministically.
- `scripts/build_windows.py`: build and audit the Windows artifact.
- `.github/workflows/deploy-frontend.yml`: deploy live route and verify assets.
- `.github/workflows/release-live-player.yml`: tests, Windows build, extension ZIP, checksums, release upload.
- `tests/pages_live/`: transport and asset-sync tests.
- `tests/test_live_release.py`: workflow and artifact-policy tests.
- `docs/live-player.md`: installation, privacy, troubleshooting, and architecture notes.

### Task 1: Pages capability detection and disconnected state

**Files:**
- Create: `frontend/live/index.html`
- Create: `frontend/live/app.css`
- Create: `frontend/live/app.js`
- Create: `tests/pages_live/app.test.mjs`

**Interfaces:**
- Consumes: `createExtensionTransport()` and `createLocalTransport()` from later tasks.
- Produces: `detectTransport(adapters)`, `renderState(state)`, and states `detecting`, `connected`, `login-required`, `empty`, `playing`, and `disconnected`.

- [ ] **Step 1: Write failing deterministic-detection tests**

```javascript
import test from "node:test";
import assert from "node:assert/strict";
import { detectTransport } from "../../frontend/live/app.js";

test("prefers the extension transport", async () => {
  const transport = await detectTransport([
    { name: "extension", probe: async () => true },
    { name: "local", probe: async () => true },
  ]);
  assert.equal(transport.name, "extension");
});

test("returns disconnected when no helper is available", async () => {
  const transport = await detectTransport([{ name: "extension", probe: async () => false }]);
  assert.equal(transport, null);
});
```

- [ ] **Step 2: Run and verify RED**

Run: `node --test tests/pages_live/app.test.mjs`

Expected: module-not-found failure.

- [ ] **Step 3: Implement the shell and pure state functions**

```javascript
export async function detectTransport(adapters) {
  for (const adapter of adapters) {
    try {
      if (await adapter.probe()) return adapter;
    } catch (_) {}
  }
  return null;
}
```

The disconnected view must explain that Pages has no cloud proxy and offer exactly two actions: install/open the Edge extension, or launch the Windows local player. It must not show credential fields.

- [ ] **Step 4: Implement the approved visual system**

Use the same deep ink, paper, live green, and amber tokens as the local UI. Desktop uses a 280px live-course rail and flexible player surface; below 760px, the rail becomes a drawer. Every connection change uses visible text in an `aria-live="polite"` region; color is never the only indicator.

```css
:root { --ink: #0b1736; --paper: #f4f0e7; --live: #35d07f; --warn: #f0b44d; }
.live-shell { min-height: 100dvh; display: grid; grid-template-columns: 280px minmax(0, 1fr); background: var(--ink); }
@media (max-width: 759px) {
  .live-shell { grid-template-columns: 1fr; }
  .course-rail { position: fixed; inset: 0 20% 0 0; transform: translateX(-100%); }
  .course-rail[data-open="true"] { transform: translateX(0); }
}
```

- [ ] **Step 5: Run tests and commit**

Run: `node --test tests/pages_live/app.test.mjs`

Expected: all tests pass.

```bash
git add -f frontend/live tests/pages_live/app.test.mjs
git commit -m "feat: add live Pages connection shell"
```

### Task 2: Edge extension transport and embedded player frame

**Files:**
- Create: `frontend/live/transports/extension.js`
- Create: `tests/pages_live/extension.test.mjs`
- Modify: `frontend/live/app.js`

**Interfaces:**
- Consumes: Edge extension protocol version 1 and its externally connectable player resource.
- Produces: `createExtensionTransport({extensionId, runtime})` with `probe()`, `listLive()`, `mountPlayer(container, course, view)`, `setView(view)`, and `refresh()`.

- [ ] **Step 1: Write failing origin and nonce tests**

```javascript
test("mount accepts READY only from the configured extension origin and nonce", async () => {
  const transport = createExtensionTransport({ extensionId: EXTENSION_ID, runtime: fakeRuntime });
  const mounted = transport.mountPlayer(container, course, "teacher");
  dispatchMessage({ origin: "https://evil.invalid", data: { type: "LIVE_PLAYER_READY", nonce: mounted.nonce } });
  assert.equal(mounted.ready, false);
  dispatchMessage({ origin: `chrome-extension://${EXTENSION_ID}`, data: { type: "LIVE_PLAYER_READY", nonce: mounted.nonce } });
  assert.equal(mounted.ready, true);
});
```

- [ ] **Step 2: Run and verify RED**

Run: `node --test tests/pages_live/extension.test.mjs`

Expected: transport module is missing.

- [ ] **Step 3: Implement extension probing and frame mounting**

Probe with a versioned `CAPABILITIES` message to the fixed extension ID produced by the public manifest key. On success, request only safe course metadata. Mount the extension's web-accessible `player/index.html` iframe with no signed data in the URL; pass `{courseId, subId, view, nonce}` by `postMessage` after the frame announces readiness. Pin `targetOrigin` to `chrome-extension://<extension-id>` in both directions.

```javascript
export function createExtensionTransport({ extensionId, runtime }) {
  const origin = `chrome-extension://${extensionId}`;
  return {
    name: "extension",
    probe: async () => Boolean(await runtime.sendMessage(extensionId, { version: 1, type: "CAPABILITIES" })),
    mountPlayer(container) {
      const frame = document.createElement("iframe");
      frame.src = `${origin}/player/index.html`;
      frame.allow = "autoplay; fullscreen";
      container.replaceChildren(frame);
      return frame;
    },
  };
}
```

- [ ] **Step 4: Run transport tests and commit**

Run: `node --test tests/pages_live/extension.test.mjs tests/pages_live/app.test.mjs`

Expected: all tests pass.

```bash
git add -f frontend/live tests/pages_live
git commit -m "feat: connect Pages to Edge live player"
```

### Task 3: Explicit local-bridge pairing fallback

**Files:**
- Create: `frontend/live/transports/local.js`
- Create: `tests/pages_live/local.test.mjs`
- Modify: `live_player/cli.py`
- Modify: `live_player/server/app.py`
- Create: `tests/live_server/test_pages_pairing.py`

**Interfaces:**
- Produces: `python -m live_player.cli --pages`, a fragment handoff `#bridge=<encoded-loopback-origin>&bootstrap=<one-use-token>`, and `createLocalTransport(location, fetcher)`.

- [ ] **Step 1: Write failing fragment and origin tests**

```javascript
test("local transport reads pairing only from the fragment", () => {
  const transport = createLocalTransport(
    new URL("https://johnxmj.github.io/Fudan_iCourse_Subscriber/live/#bridge=http%3A%2F%2F127.0.0.1%3A43123&bootstrap=once"),
    fakeFetch,
  );
  assert.equal(transport.baseUrl, "http://127.0.0.1:43123");
  assert.equal(transport.bootstrap, "once");
});

test("rejects non-loopback bridge origins", () => {
  assert.throws(() => createLocalTransport(new URL("https://example.test/#bridge=https%3A%2F%2Fevil.invalid&bootstrap=x"), fakeFetch), /loopback/);
});
```

```python
def test_pages_origin_is_allowed_only_for_pairing(self):
    response = self.options("/api/session", origin="https://johnxmj.github.io", private_network=True)
    self.assertEqual(response.headers["Access-Control-Allow-Origin"], "https://johnxmj.github.io")
    self.assertEqual(response.headers["Access-Control-Allow-Private-Network"], "true")
```

- [ ] **Step 2: Run and verify RED**

Run: `node --test tests/pages_live/local.test.mjs && python -m unittest tests.live_server.test_pages_pairing -v`

Expected: missing transport and missing CORS/PNA headers.

- [ ] **Step 3: Implement safe pairing**

`--pages` opens the public Pages live route with pairing values in the fragment; URL fragments are not sent to GitHub. Pages validates the bridge hostname is exactly `127.0.0.1` or `[::1]`, exchanges the one-use bootstrap token, calls `history.replaceState()` immediately to remove the fragment, and retains only the process-lifetime bearer token in memory.

The loopback server answers `OPTIONS` for the exact Pages origin with `Access-Control-Allow-Methods: GET, POST, OPTIONS`, `Access-Control-Allow-Headers: Authorization, Content-Type`, `Access-Control-Allow-Private-Network: true`, and `Vary: Origin`. It returns no CORS headers for any other origin.

```javascript
function parseBridge(location) {
  const params = new URLSearchParams(location.hash.slice(1));
  const baseUrl = new URL(params.get("bridge"));
  if (!new Set(["127.0.0.1", "[::1]"]).has(baseUrl.hostname)) throw new TypeError("bridge must use loopback");
  if (!params.get("bootstrap")) throw new TypeError("bootstrap token is required");
  return { baseUrl: baseUrl.origin, bootstrap: params.get("bootstrap") };
}
```

- [ ] **Step 4: Run pairing tests and commit**

Run: `node --test tests/pages_live/local.test.mjs && python -m unittest tests.live_server.test_pages_pairing -v`

Expected: all tests pass.

```bash
git add -f frontend/live live_player/cli.py live_player/server/app.py tests/pages_live tests/live_server/test_pages_pairing.py
git commit -m "feat: pair Pages with local live bridge"
```

### Task 4: Shared asset synchronization and existing frontend link

**Files:**
- Create: `scripts/sync_live_web.mjs`
- Create: `tests/pages_live/sync.test.mjs`
- Modify: `frontend/index.html`
- Modify: `frontend/live/index.html`
- Create: `frontend/live/vendor/hls.min.js`

**Interfaces:**
- Produces: `node scripts/sync_live_web.mjs --check` and `node scripts/sync_live_web.mjs --write`.

- [ ] **Step 1: Write failing synchronization tests**

```javascript
test("Pages HLS asset matches the pinned local-player asset", () => {
  assert.equal(
    createHash("sha256").update(readFileSync("frontend/live/vendor/hls.min.js")).digest("hex"),
    createHash("sha256").update(readFileSync("live_player/web/vendor/hls.min.js")).digest("hex"),
  );
});
```

- [ ] **Step 2: Run and verify RED**

Run: `node --test tests/pages_live/sync.test.mjs`

Expected: Pages vendor asset is missing.

- [ ] **Step 3: Implement an allowlisted sync script**

The script copies only the pinned HLS.js distribution and license plus explicitly shared CSS tokens. `--check` compares SHA-256 hashes and exits nonzero on drift; `--write` updates the Pages copies. Add a clearly labeled “当前直播” link to the existing frontend header without changing database setup or summary routes.

```javascript
const FILES = new Map([
  ["live_player/web/vendor/hls.min.js", "frontend/live/vendor/hls.min.js"],
  ["live_player/web/vendor/LICENSE", "frontend/live/vendor/LICENSE"],
]);
```

- [ ] **Step 4: Run tests and commit**

Run: `node scripts/sync_live_web.mjs --write && node scripts/sync_live_web.mjs --check && node --test tests/pages_live/*.test.mjs`

Expected: sync check and all Pages tests pass.

```bash
git add -f scripts/sync_live_web.mjs frontend tests/pages_live
git commit -m "feat: share live assets with GitHub Pages"
```

### Task 5: Deployment and release workflows

**Files:**
- Modify: `.github/workflows/deploy-frontend.yml`
- Create: `.github/workflows/release-live-player.yml`
- Create: `scripts/build_windows.py`
- Create: `tests/test_live_release.py`
- Create: `requirements-live-build.txt`

**Interfaces:**
- Produces: Pages deployment validation, `dist/fudan-icourse-live-player.exe`, `dist/fudan-icourse-live-edge.zip`, and SHA-256 checksums on version tags matching `live-v*`.

- [ ] **Step 1: Write failing workflow-policy tests**

```python
class LiveReleaseWorkflowTest(unittest.TestCase):
    def test_release_runs_tests_before_packaging(self):
        text = Path(".github/workflows/release-live-player.yml").read_text(encoding="utf-8")
        self.assertLess(text.index("python -m unittest"), text.index("Build Windows player"))
        self.assertLess(text.index("node --test"), text.index("Package Edge extension"))

    def test_artifact_allowlist_excludes_private_files(self):
        from scripts.build_windows import is_allowed_artifact_input
        self.assertFalse(is_allowed_artifact_input(Path(".env")))
        self.assertFalse(is_allowed_artifact_input(Path("data/icourse.db")))
        self.assertTrue(is_allowed_artifact_input(Path("live_player/web/index.html")))
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m unittest tests.test_live_release -v`

Expected: release workflow and build module are missing.

- [ ] **Step 3: Implement the Windows build allowlist**

Use `requirements-live-build.txt` with `pyinstaller>=6,<7` only in the release build environment, not in the normal subscriber runtime. Build from `live_player/cli.py`, include `live_player/web` data, exclude ASR/OCR model packages from the executable, and inspect the collected files against an explicit allowlist. Fail if a path contains `.env`, `data/`, `_run_logs/`, cookies, databases, or credentials.

```python
DENIED_PARTS = {".env", "data", "_run_logs", "cookie", "cookies", "credential", "credentials"}

def is_allowed_artifact_input(path):
    lowered = {part.lower() for part in path.parts}
    return not bool(lowered & DENIED_PARTS)
```

- [ ] **Step 4: Implement CI and release ordering**

The release workflow runs on `workflow_dispatch` and `live-v*` tags. Jobs run the full Python suite, all Node tests, asset sync check, Windows build on `windows-latest`, extension build, SHA-256 generation, and GitHub Release upload. The Pages workflow runs `node scripts/sync_live_web.mjs --check` before upload and includes both `frontend/index.html` and `frontend/live/index.html` in an artifact assertion.

```yaml
on:
  workflow_dispatch:
  push:
    tags: ["live-v*"]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - uses: actions/setup-node@v4
        with: {node-version: "22"}
      - run: python -m unittest discover -s tests -v
      - run: node --test tests/live_web/*.test.mjs tests/extension/*.test.mjs tests/pages_live/*.test.mjs
```

- [ ] **Step 5: Run workflow and build tests**

Run:

```bash
python -m unittest tests.test_live_release tests.test_workflows -v
node --test tests/pages_live/*.test.mjs tests/extension/*.test.mjs
git diff --check
```

Expected: all tests pass and diff check is clean.

- [ ] **Step 6: Commit release automation**

```bash
git add -f .github/workflows scripts/build_windows.py tests/test_live_release.py requirements-live-build.txt
git commit -m "ci: package and publish live player"
```

### Task 6: Public documentation and end-to-end acceptance

**Files:**
- Create: `docs/live-player.md`
- Modify: `README.md`
- Create: `.github/ISSUE_TEMPLATE/live-player.yml`
- Create: `tests/test_live_docs.py`

**Interfaces:**
- Produces: public installation, privacy, troubleshooting, and safe bug-reporting documentation.

- [ ] **Step 1: Write failing documentation-safety tests**

```python
class LiveDocsTest(unittest.TestCase):
    def test_docs_state_pages_requires_a_local_helper(self):
        text = Path("docs/live-player.md").read_text(encoding="utf-8")
        self.assertIn("GitHub Pages 不提供云端代理", text)
        self.assertIn("Edge 扩展或本地播放器", text)

    def test_issue_template_warns_against_private_logs(self):
        text = Path(".github/ISSUE_TEMPLATE/live-player.yml").read_text(encoding="utf-8")
        for value in ("密码", "Cookie", "签名直播地址"):
            self.assertIn(value, text)
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m unittest tests.test_live_docs -v`

Expected: documentation files are missing.

- [ ] **Step 3: Write public setup and privacy documentation**

Document three entry paths, current-live-only behavior, official CAS flow, local credential handling, extension permissions, Pages helper requirement, uninstall steps, and recovery for no-live, login-required, source-expired, and WebVPN-unreachable states. State explicitly that the project neither records nor stores video.

- [ ] **Step 4: Run the complete automated verification**

Run:

```bash
python -m unittest discover -s tests -v
node --test tests/live_web/*.test.mjs tests/extension/*.test.mjs tests/pages_live/*.test.mjs
node scripts/sync_live_web.mjs --check
node edge_extension/scripts/build.mjs
python scripts/build_windows.py --audit-only
git diff --check
```

Expected: zero test failures, both build audits pass, and diff check has no output.

- [ ] **Step 5: Perform the authorized Edge acceptance matrix**

Verify:

```text
Local player: current live course lists and plays for 5+ seconds
Extension popup: same course lists and opens extension player
Pages + extension: embedded player reaches readyState >= 2 and advances
Pages + local --pages: fragment is removed after pairing and playback advances
Expired source: one refresh occurs and playback resumes
Ended course: media requests stop and UI returns to course list
No helper: Pages shows installation guidance and no credential form
```

Use a second currently live course when available; otherwise use the redacted second-course fixture and synthetic HLS endpoint. Never save or commit signed URLs, cookies, credentials, or video captures.

- [ ] **Step 6: Commit the public documentation**

```bash
git add -f README.md docs/live-player.md .github/ISSUE_TEMPLATE/live-player.yml tests/test_live_docs.py
git commit -m "docs: publish live player setup and privacy guide"
```
