# Fudan iCourse Local Live Player Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows-first local web player that discovers currently live iCourse sessions, refreshes their short-lived sources, and streams them through the user's own authenticated WebVPN session to Microsoft Edge.

**Architecture:** A small `live_player` package wraps the existing `WebVPNSession` and `ICourseClient`, exposes a loopback-only HTTP API, rewrites HLS manifests to opaque local segment routes, and serves a shared framework-free player UI. Upstream credentials and signed URLs stay in Python memory; the browser receives only local routes.

**Tech Stack:** Python 3.12, standard-library `http.server`, existing `requests` and `pycryptodome`, JavaScript ES2020, HLS.js 1.5.18, Python `unittest`, Node.js `node:test`, Microsoft Edge.

## Global Constraints

- The repository is public; never commit a student ID, password, cookie, API key, course-specific private value, or signed media URL.
- Support only sessions the platform currently marks live; do not expose gated recordings, downloads, recording, or archival.
- Bind the local service to `127.0.0.1` only.
- Keep credentials, WebVPN cookies, signed URLs, and segment mappings in process memory and redact them from logs.
- Do not persist media bytes.
- Open Microsoft Edge by default on Windows.
- Vendor the pinned HLS.js runtime; the live feature must not require a public CDN at runtime.
- Keep the existing subscriber and summary workflow operational.

---

## File Map

- `live_player/__init__.py`: package version and public exports.
- `live_player/core/models.py`: stable live-course and source-view dataclasses.
- `live_player/core/catalog.py`: course-ID resolution and current-live filtering.
- `live_player/core/sources.py`: source selection and HLS manifest rewriting.
- `live_player/core/session.py`: bounded WebVPN/iCourse session lifecycle.
- `live_player/core/redaction.py`: secret and signed-URL-safe diagnostics.
- `live_player/server/tokens.py`: bootstrap and opaque segment token stores.
- `live_player/server/app.py`: loopback API, static assets, manifests, and streaming segments.
- `live_player/server/handler.py`: HTTP request parsing and response serialization.
- `live_player/web/index.html`: local live-player shell.
- `live_player/web/app.css`: responsive academic control-desk visual system.
- `live_player/web/app.js`: local transport, course selection, HLS lifecycle, and recovery.
- `live_player/web/vendor/hls.min.js`: pinned HLS.js 1.5.18 distribution.
- `live_player/web/vendor/LICENSE`: HLS.js license.
- `live_player/cli.py`: configuration, server startup, Edge launch, and shutdown.
- `tests/live_core/`: core unit tests and redacted fixtures.
- `tests/live_server/`: loopback server integration tests.
- `tests/live_web/`: pure JavaScript tests.

### Task 1: Stable live-session model and filtering

**Files:**
- Create: `live_player/__init__.py`
- Create: `live_player/core/__init__.py`
- Create: `live_player/core/models.py`
- Create: `live_player/core/catalog.py`
- Create: `tests/live_core/test_catalog.py`
- Create: `tests/live_core/fixtures.py`

**Interfaces:**
- Consumes: `ICourseClient.get_course_detail(course_id: str) -> dict`, `ICourseClient.get_sub_info(course_id: str, sub_id: str) -> dict`, and `ICourseClient.list_semester_courses(term: str) -> list[dict]`.
- Produces: `LiveCourse`, `resolve_course_ids(client, configured_ids, term)`, `map_live_course(course_id, course_detail, sub_info)`, and `discover_live_courses(client, course_ids)`.

- [ ] **Step 1: Write redacted fixtures and failing model tests**

```python
# tests/live_core/test_catalog.py
import unittest

from live_player.core.catalog import discover_live_courses, map_live_course
from tests.live_core.fixtures import COURSE_DETAIL, LIVE_INFO, ENDED_INFO


class FakeClient:
    def __init__(self, infos):
        self.infos = infos

    def get_course_detail(self, course_id):
        return COURSE_DETAIL

    def get_sub_info(self, course_id, sub_id):
        return self.infos[str(sub_id)]


class LiveCatalogTest(unittest.TestCase):
    def test_maps_current_live_session_without_upstream_urls(self):
        course = map_live_course("38463", COURSE_DETAIL, LIVE_INFO)
        self.assertEqual(course.course_id, "38463")
        self.assertEqual(course.sub_id, "655212")
        self.assertEqual(course.status, "live")
        self.assertEqual(course.available_views, ("teacher", "student", "teacher_audio", "student_audio"))
        self.assertNotIn("http", repr(course))

    def test_discovers_only_platform_live_sessions(self):
        client = FakeClient({"655212": LIVE_INFO, "655213": ENDED_INFO})
        courses = discover_live_courses(client, ["38463"])
        self.assertEqual([c.sub_id for c in courses], ["655212"])


if __name__ == "__main__":
    unittest.main()
```

Fixtures use invented IDs and replace every media URL with `https://media.invalid/...`; `LIVE_INFO["sub_status"]` is `1` and `ENDED_INFO["sub_status"]` is `2`.

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m unittest tests.live_core.test_catalog -v`

Expected: import failure for `live_player.core.catalog` because the package does not exist.

- [ ] **Step 3: Implement the minimal dataclasses and catalog mapping**

```python
# live_player/core/models.py
from dataclasses import dataclass


@dataclass(frozen=True)
class LiveCourse:
    course_id: str
    course_title: str
    teacher: str
    room: str
    sub_id: str
    sub_title: str
    starts_at: str
    ends_at: str
    status: str
    available_views: tuple[str, ...]


LIVE_STATUS = 1
```

```python
# live_player/core/catalog.py
from .models import LIVE_STATUS, LiveCourse

VIEW_PATHS = {
    "teacher": ("output", "m3u8"),
    "student": ("output_student", "m3u8"),
    "teacher_audio": ("output", "m3u8_audio"),
    "student_audio": ("output_student", "m3u8_audio"),
}


def _nested(mapping, path):
    value = mapping
    for key in path:
        value = value.get(key, {}) if isinstance(value, dict) else {}
    return value


def map_live_course(course_id, course_detail, sub_info):
    if int(sub_info.get("sub_status", -1)) != LIVE_STATUS:
        return None
    live_url = sub_info.get("live_url") or {}
    views = tuple(name for name, path in VIEW_PATHS.items() if _nested(live_url, path))
    if not views:
        return None
    return LiveCourse(
        course_id=str(course_id),
        course_title=sub_info.get("course_title") or course_detail.get("title", ""),
        teacher=sub_info.get("lecturer_name") or course_detail.get("teacher", ""),
        room=sub_info.get("room_name") or "",
        sub_id=str(sub_info["sub_id"]),
        sub_title=sub_info.get("sub_title") or "",
        starts_at=str(sub_info.get("start_at") or sub_info.get("begin_time") or ""),
        ends_at=str(sub_info.get("end_at") or sub_info.get("end_time") or ""),
        status="live",
        available_views=views,
    )
```

Implement `discover_live_courses()` by walking the course detail's lectures, requesting only the newest lecture whose date is today or whose end time has not elapsed, and keeping non-`None` mappings. Implement `resolve_course_ids()` so configured IDs win; when empty, use the newest result from `discover_terms()` and `list_semester_courses()`.

```python
def discover_live_courses(client, course_ids):
    live = []
    for course_id in course_ids:
        detail = client.get_course_detail(str(course_id))
        for lecture in reversed(detail.get("lectures", [])):
            info = client.get_sub_info(str(course_id), str(lecture["sub_id"]))
            mapped = map_live_course(str(course_id), detail, info)
            if mapped is not None:
                live.append(mapped)
                break
    return sorted(live, key=lambda item: item.starts_at)
```

- [ ] **Step 4: Run the catalog tests and verify GREEN**

Run: `python -m unittest tests.live_core.test_catalog -v`

Expected: 2 tests pass.

- [ ] **Step 5: Commit the model increment**

```bash
git add -f live_player tests/live_core
git commit -m "feat: model current iCourse live sessions"
```

### Task 2: Source resolution and HLS manifest rewriting

**Files:**
- Create: `live_player/core/sources.py`
- Create: `tests/live_core/test_sources.py`

**Interfaces:**
- Consumes: `ICourseClient.get_sub_info()` and `src.api.webvpn.get_vpn_url()`.
- Produces: `LiveSourceResolver.resolve(course_id: str, sub_id: str, view: str) -> str` and `rewrite_hls_manifest(text: str, register: Callable[[str], str], base_url: str) -> str`.

- [ ] **Step 1: Write failing source and manifest tests**

```python
# tests/live_core/test_sources.py
import unittest

from live_player.core.sources import LiveSourceResolver, rewrite_hls_manifest


class FakeClient:
    def get_sub_info(self, course_id, sub_id):
        return {"sub_status": 1, "live_url": {"output": {"m3u8": "https://media.invalid/live/main.m3u8"}}}


class SourceTest(unittest.TestCase):
    def test_rejects_unknown_view(self):
        with self.assertRaisesRegex(ValueError, "unknown live view"):
            LiveSourceResolver(FakeClient()).resolve("1", "2", "screen")

    def test_rewrites_absolute_and_relative_segments(self):
        manifest = "#EXTM3U\n#EXTINF:10,\nseg-1.ts?sig=secret\n#EXTINF:10,\nhttps://media.invalid/live/seg-2.ts?sig=secret\n"
        seen = []
        output = rewrite_hls_manifest(manifest, lambda url: seen.append(url) or f"/media/segment/{len(seen)}", "https://media.invalid/live/main.m3u8")
        self.assertIn("/media/segment/1", output)
        self.assertIn("/media/segment/2", output)
        self.assertEqual(seen[0], "https://media.invalid/live/seg-1.ts?sig=secret")
        self.assertNotIn("sig=secret", output)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m unittest tests.live_core.test_sources -v`

Expected: import failure for `live_player.core.sources`.

- [ ] **Step 3: Implement source resolution and line-preserving manifest rewriting**

```python
# live_player/core/sources.py
from urllib.parse import urljoin

from src.api.webvpn import get_vpn_url

SOURCE_PATHS = {
    "teacher": ("output", "m3u8"),
    "student": ("output_student", "m3u8"),
    "teacher_audio": ("output", "m3u8_audio"),
    "student_audio": ("output_student", "m3u8_audio"),
}


class LiveSourceResolver:
    def __init__(self, client):
        self.client = client

    def resolve(self, course_id, sub_id, view):
        if view not in SOURCE_PATHS:
            raise ValueError(f"unknown live view: {view}")
        info = self.client.get_sub_info(course_id, sub_id)
        if int(info.get("sub_status", -1)) != 1:
            raise RuntimeError("lecture is not currently live")
        value = info.get("live_url") or {}
        for key in SOURCE_PATHS[view]:
            value = value.get(key) if isinstance(value, dict) else None
        if not isinstance(value, str) or not value.startswith("https://"):
            raise RuntimeError(f"live view unavailable: {view}")
        return get_vpn_url(value)


def rewrite_hls_manifest(text, register, base_url):
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            lines.append(raw)
        else:
            lines.append(register(urljoin(base_url, line)))
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
```

Extend the rewriter in the same test-first cycle for URI-bearing tags such as `#EXT-X-KEY` and `#EXT-X-MAP`, replacing only their quoted `URI` attribute with an opaque local route.

```python
_URI_ATTRIBUTE = re.compile(r'URI="([^"]+)"')

def _rewrite_uri_attribute(line, register, base_url):
    return _URI_ATTRIBUTE.sub(
        lambda match: f'URI="{register(urljoin(base_url, match.group(1)))}"',
        line,
    )
```

- [ ] **Step 4: Run source tests and the existing suite**

Run: `python -m unittest tests.live_core.test_sources -v && python -m unittest discover -s tests -v`

Expected: all tests pass.

- [ ] **Step 5: Commit the source increment**

```bash
git add -f live_player/core/sources.py tests/live_core/test_sources.py
git commit -m "feat: resolve and rewrite current live streams"
```

### Task 3: Bounded session lifecycle and safe diagnostics

**Files:**
- Create: `live_player/core/session.py`
- Create: `live_player/core/redaction.py`
- Create: `tests/live_core/test_session.py`
- Create: `tests/live_core/test_redaction.py`

**Interfaces:**
- Produces: `SessionManager.get_client()`, `SessionManager.invalidate()`, `SessionManager.call(operation)`, and `redact_message(value: object) -> str`.

- [ ] **Step 1: Write failing bounded-retry and redaction tests**

```python
class SessionManagerTest(unittest.TestCase):
    def test_reauthenticates_once_after_a_cold_session(self):
        factory = FakeFactory([False, True])
        manager = SessionManager(factory, max_login_attempts=2)
        self.assertEqual(manager.call(lambda client: "ok"), "ok")
        self.assertEqual(factory.calls, 2)

    def test_never_logs_credentials_or_signed_query(self):
        value = redact_message("login 22300000000 password=secret https://media.invalid/a.ts?auth_key=abc&t=def")
        self.assertNotIn("secret", value)
        self.assertNotIn("abc", value)
        self.assertNotIn("def", value)
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m unittest tests.live_core.test_session tests.live_core.test_redaction -v`

Expected: imports fail because the modules do not exist.

- [ ] **Step 3: Implement a lock-protected manager with exactly two login attempts**

`SessionManager` stores one client, guards login with `threading.RLock`, calls `check_alive()` before reuse, and retries authentication only up to `max_login_attempts`. `invalidate()` drops references to both client and session. `redact_message()` replaces password-like fields and query values for `auth_key`, `token`, `sign`, `clientUUID`, and `t` with `[redacted]`.

```python
class SessionManager:
    def __init__(self, factory, max_login_attempts=2):
        self.factory = factory
        self.max_login_attempts = max_login_attempts
        self._client = None
        self._lock = threading.RLock()

    def get_client(self):
        with self._lock:
            if self._client is not None and self._client.check_alive():
                return self._client
            self._client = None
            last_error = None
            for _ in range(self.max_login_attempts):
                try:
                    self._client = self.factory()
                    return self._client
                except Exception as error:
                    last_error = error
            raise RuntimeError(redact_message(last_error)) from None
```

- [ ] **Step 4: Run the focused and full tests**

Run: `python -m unittest tests.live_core.test_session tests.live_core.test_redaction -v && python -m unittest discover -s tests -v`

Expected: all tests pass and output contains no fixture secrets.

- [ ] **Step 5: Commit the session increment**

```bash
git add -f live_player/core/session.py live_player/core/redaction.py tests/live_core
git commit -m "feat: manage live WebVPN sessions safely"
```

### Task 4: Opaque token stores and loopback API

**Files:**
- Create: `live_player/server/__init__.py`
- Create: `live_player/server/tokens.py`
- Create: `live_player/server/app.py`
- Create: `live_player/server/handler.py`
- Create: `tests/live_server/test_tokens.py`
- Create: `tests/live_server/test_api.py`

**Interfaces:**
- Produces: `TokenStore.issue(value, ttl_seconds) -> str`, `TokenStore.consume(token)`, `LiveApplication.handle(method, path, headers, body) -> Response`, and `serve(application, host="127.0.0.1", port=0)`.

- [ ] **Step 1: Write failing one-use and API authorization tests**

```python
class TokenStoreTest(unittest.TestCase):
    def test_bootstrap_token_is_one_use(self):
        store = TokenStore(clock=lambda: 100)
        token = store.issue({"kind": "bootstrap"}, ttl_seconds=30)
        self.assertEqual(store.consume(token), {"kind": "bootstrap"})
        self.assertIsNone(store.consume(token))


class LiveApiTest(unittest.TestCase):
    def test_rejects_course_list_without_session_token(self):
        response = self.app.handle("GET", "/api/live-courses", {}, b"")
        self.assertEqual(response.status, 401)

    def test_returns_only_safe_course_fields(self):
        response = self.authorized_get("/api/live-courses")
        payload = json.loads(response.body)
        self.assertEqual(payload[0]["status"], "live")
        self.assertNotIn("live_url", response.body.decode())
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m unittest tests.live_server.test_tokens tests.live_server.test_api -v`

Expected: imports fail because `live_player.server` does not exist.

- [ ] **Step 3: Implement response routing and authorization**

Use a small immutable `Response(status, headers, body)` dataclass. `POST /api/session` consumes the launcher bootstrap token and returns a process-lifetime bearer token. All other API/media routes require `Authorization: Bearer <token>`. JSON error bodies use stable codes: `LOGIN_REQUIRED`, `NO_LIVE_COURSES`, `VIEW_UNAVAILABLE`, `SOURCE_EXPIRED`, and `UPSTREAM_FAILED`.

```python
@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes = b""
    body_iter: object | None = None


def _error(status, code, message):
    body = json.dumps({"error": {"code": code, "message": message}}).encode()
    return Response(status, {"Content-Type": "application/json", "Cache-Control": "no-store"}, body)
```

- [ ] **Step 4: Run API tests and full Python suite**

Run: `python -m unittest tests.live_server.test_tokens tests.live_server.test_api -v && python -m unittest discover -s tests -v`

Expected: all tests pass.

- [ ] **Step 5: Commit the API increment**

```bash
git add -f live_player/server tests/live_server
git commit -m "feat: add authenticated loopback live API"
```

### Task 5: Manifest and segment streaming proxy

**Files:**
- Modify: `live_player/server/app.py`
- Modify: `live_player/server/handler.py`
- Create: `tests/live_server/test_media_proxy.py`

**Interfaces:**
- Consumes: `LiveSourceResolver.resolve()` and `rewrite_hls_manifest()`.
- Produces: `/media/{course_id}/{sub_id}/{view}/manifest.m3u8` and `/media/segment/{opaque_id}`.

- [ ] **Step 1: Write failing media-proxy tests**

```python
class MediaProxyTest(unittest.TestCase):
    def test_manifest_hides_every_upstream_url(self):
        response = self.authorized_get("/media/38463/655212/teacher/manifest.m3u8")
        text = response.body.decode()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["Content-Type"], "application/vnd.apple.mpegurl")
        self.assertIn("/media/segment/", text)
        self.assertNotIn("media.invalid", text)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_segment_stream_is_not_written_to_disk(self):
        token = self.first_segment_token()
        before = set(Path(self.tempdir.name).rglob("*"))
        response = self.authorized_get(f"/media/segment/{token}")
        self.assertEqual(b"".join(response.body_iter), b"video-bytes")
        self.assertEqual(set(Path(self.tempdir.name).rglob("*")), before)
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m unittest tests.live_server.test_media_proxy -v`

Expected: the manifest route returns 404.

- [ ] **Step 3: Implement streaming with short-lived opaque segment mappings**

Fetch the fresh manifest through `WebVPNSession.get_raw()`, register each upstream URI for 90 seconds, and rewrite it to a local segment route. The segment handler streams `iter_content(64 * 1024)`, forwards only `Content-Type`, `Content-Length`, and `Accept-Ranges`, applies `Cache-Control: no-store`, and closes the upstream response on client cancellation. On upstream 401/403, invalidate the source once and return `SOURCE_EXPIRED` without logging the URL.

```python
def _stream_chunks(response):
    try:
        for chunk in response.iter_content(64 * 1024):
            if chunk:
                yield chunk
    finally:
        response.close()
```

- [ ] **Step 4: Run proxy and full Python tests**

Run: `python -m unittest tests.live_server.test_media_proxy -v && python -m unittest discover -s tests -v`

Expected: all tests pass with no temporary media files.

- [ ] **Step 5: Commit the media increment**

```bash
git add -f live_player/server tests/live_server/test_media_proxy.py
git commit -m "feat: proxy live HLS without persisting media"
```

### Task 6: Shared local UI and HLS recovery

**Files:**
- Create: `live_player/web/index.html`
- Create: `live_player/web/app.css`
- Create: `live_player/web/app.js`
- Create: `live_player/web/transport-local.js`
- Create: `live_player/web/vendor/hls.min.js`
- Create: `live_player/web/vendor/LICENSE`
- Create: `tests/live_web/app.test.mjs`
- Create: `tests/live_web/transport-local.test.mjs`

**Interfaces:**
- Consumes: the local API from Tasks 4-5.
- Produces: `window.LivePlayerApp`, `createLocalTransport(baseUrl, token)`, and a transport-neutral UI contract reused by later plans.

- [ ] **Step 1: Write failing JavaScript state and transport tests**

```javascript
// tests/live_web/app.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { nextRecoveryAction } from "../../live_player/web/app.js";

test("refreshes source after repeated fragment failures", () => {
  assert.equal(nextRecoveryAction({ fragmentFailures: 3, sessionExpired: false }), "refresh-source");
});

test("requires login when session has expired", () => {
  assert.equal(nextRecoveryAction({ fragmentFailures: 0, sessionExpired: true }), "login-required");
});
```

- [ ] **Step 2: Run and verify RED**

Run: `node --test tests/live_web/*.test.mjs`

Expected: module-not-found failure for `live_player/web/app.js`.

- [ ] **Step 3: Implement the framework-free interface**

Use semantic HTML with a live-course rail, a large `<video>` region, status text with `aria-live="polite"`, view buttons, refresh, and full-screen controls. Export pure state helpers for tests. Create the HLS instance with `liveSyncDurationCount: 2`, recover a fatal network error by calling the refresh endpoint once, and recover a fatal media error once with `hls.recoverMediaError()` before surfacing failure.

```javascript
export function nextRecoveryAction(state) {
  if (state.sessionExpired) return "login-required";
  if (state.fragmentFailures >= 3) return "refresh-source";
  return "retry-fragment";
}

export function createHls(Hls, onFatal) {
  const hls = new Hls({ liveSyncDurationCount: 2, backBufferLength: 30 });
  hls.on(Hls.Events.ERROR, (_event, data) => data.fatal && onFatal(data));
  return hls;
}
```

The design uses deep ink blue (`#0b1736`), paper (`#f4f0e7`), live green (`#35d07f`), warning amber (`#f0b44d`), and source-serif headings with system sans-serif controls. At widths below 760px, the course rail becomes a modal drawer and the player remains the first visual element.

- [ ] **Step 4: Vendor HLS.js and record its license**

Fetch `hls.min.js` and `LICENSE` from the official `video-dev/hls.js` v1.5.18 release, verify the release tag, store both under `live_player/web/vendor/`, and add a test that asserts `Hls.version` text or the distribution banner contains `1.5.18`.

- [ ] **Step 5: Run JavaScript tests**

Run: `node --test tests/live_web/*.test.mjs`

Expected: all JavaScript tests pass.

- [ ] **Step 6: Commit the UI increment**

```bash
git add -f live_player/web tests/live_web
git commit -m "feat: add responsive local live player UI"
```

### Task 7: Launcher, configuration, and Windows smoke path

**Files:**
- Create: `live_player/cli.py`
- Create: `tests/live_server/test_cli.py`
- Modify: `.env.example`
- Modify: `README.md`

**Interfaces:**
- Produces: `python -m live_player.cli`, `build_application(env)`, and `open_edge(url)`.

- [ ] **Step 1: Write failing launcher tests**

```python
class LauncherTest(unittest.TestCase):
    def test_server_uses_loopback_and_ephemeral_port(self):
        config = build_application({"StuId": "user", "UISPsw": "pass", "COURSE_IDS": "1,2"})
        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 0)

    def test_missing_credentials_returns_configuration_error(self):
        with self.assertRaisesRegex(ValueError, "StuId and UISPsw"):
            build_application({})
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m unittest tests.live_server.test_cli -v`

Expected: import failure for `live_player.cli`.

- [ ] **Step 3: Implement the launcher**

Read `StuId`, `UISPsw`, and optional `COURSE_IDS` from the environment; never print their values. Start the server on `127.0.0.1:0`, create a 60-second one-use bootstrap token, and open:

```text
http://127.0.0.1:<selected-port>/?bootstrap=<one-use-token>
```

On Windows, locate Edge under the two standard Program Files locations and launch it with `subprocess.Popen([edge_path, url])`. Fall back to `webbrowser.open(url)` only when Edge is absent. Handle Ctrl+C by closing the HTTP server, invalidating the session manager, and clearing all token stores.

```python
def open_edge(url):
    candidates = [
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Microsoft/Edge/Application/msedge.exe",
    ]
    edge = next((path for path in candidates if path.is_file()), None)
    if edge:
        subprocess.Popen([str(edge), url])
    else:
        webbrowser.open(url)
```

- [ ] **Step 4: Document local setup and supported behavior**

Add a README section with environment-variable placeholders, `python -m live_player.cli`, the current-live-only limitation, no-recording behavior, Edge requirement, and troubleshooting for CAS, no-live-course, and session-expiry states.

- [ ] **Step 5: Run complete local-player verification**

Run:

```bash
python -m unittest discover -s tests -v
node --test tests/live_web/*.test.mjs
python -m live_player.cli --help
git diff --check
```

Expected: all tests pass, help exits 0, and `git diff --check` has no output.

- [ ] **Step 6: Perform the authorized Edge smoke test**

With local credentials supplied through environment variables, start the player and verify one current session reaches `readyState >= 2`, `videoWidth > 0`, and advances `currentTime` over five seconds. If no second course is live, run the second-course fixture through the local API and synthetic HLS manifest. Do not capture or commit signed URLs, cookies, or credentials.

- [ ] **Step 7: Commit the local-player slice**

```bash
git add -f live_player tests/live_core tests/live_server tests/live_web .env.example README.md
git commit -m "feat: launch current iCourse streams locally"
```
