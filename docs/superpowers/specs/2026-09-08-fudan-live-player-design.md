# Fudan iCourse Live Player Design

Date: 2026-09-08
Status: awaiting written-spec review

## Purpose

Extend the public `Fudan_iCourse_Subscriber` repository with a reusable player for iCourse lectures that are currently live. The project will support three user-facing entry points while sharing one product model and one web interface:

1. A Windows local player that opens in Microsoft Edge.
2. A Microsoft Edge extension.
3. A GitHub Pages interface that works through either the extension or, where browser private-network policy permits it, the local bridge.

The player must work away from the campus network by using the user's authenticated Fudan WebVPN access. It must refresh short-lived live URLs automatically, without asking users to copy media URLs.

## Scope

### In scope

- Discover courses and lecture sessions available to the signed-in account.
- Emphasize sessions whose platform state is currently live.
- Show course title, instructor, room, start time, and live status.
- Play the teacher view by default.
- Offer student view, teacher audio, and student audio when those sources exist.
- Refresh an expired media URL and resume close to the live edge.
- Recover from a cold or expired WebVPN/iCourse session through a bounded authentication flow.
- Publish source code, documentation, Windows artifacts, and the Edge extension from one public repository.
- Keep the existing subscriber and summary workflow operational.

### Out of scope

- Opening a recording before the platform marks it available.
- Bypassing playback-release gates.
- Downloading, recording, archiving, or redistributing lecture media.
- Operating a shared cloud media proxy or storing credentials on a server.
- Making GitHub Pages play video with no local player, extension, or cloud backend.

## Constraints

- The repository is public. No student ID, password, cookie, media signature, API key, or course-specific private value may be committed.
- Authentication material remains on the user's machine and is held in memory while possible.
- Media manifests and segments must flow through the user's own WebVPN session.
- The local service listens only on a loopback address.
- The first supported browser is Microsoft Edge on Windows.
- The live feature must not depend on a public CDN at runtime; pinned player assets are distributed with the repository.

## Architecture

```text
live_player/
├── core/          WebVPN login, course discovery, live-source refresh, URL rewriting
├── server/        Loopback HTTP API and streaming proxy
├── web/           Shared course list and HLS player
└── cli.py         One-command launcher that opens Edge

edge_extension/
├── manifest.json  Manifest V3 metadata and narrow host permissions
├── background.js  WebVPN requests, session checks, and message handling
└── popup/         Compact course list and launch controls

frontend/
└── live/          GitHub Pages build of the shared web interface

tests/
├── live_core/
├── live_server/
└── extension/
```

The implementation reuses the repository's existing Python `WebVPNSession` and `ICourseClient` instead of introducing a second authentication stack. The browser interface stays in plain HTML, CSS, and JavaScript so the local player, extension, and Pages deployment can share it without a framework-specific build system.

## Components

### Live core

The live core is the only Python layer that understands iCourse response shapes. It converts raw course and session payloads into a small stable model:

```text
LiveCourse
  course_id
  course_title
  teacher
  room
  sub_id
  sub_title
  starts_at
  ends_at
  status
  available_views
```

It is responsible for:

- Enumerating the configured or account-visible courses.
- Selecting only sessions whose platform status is currently live.
- Fetching fresh source metadata on demand.
- Mapping platform source names to stable view identifiers.
- Converting iCourse manifest and segment URLs into WebVPN URLs.
- Detecting session expiry without repeatedly submitting credentials.

It never returns signed upstream URLs to the UI. The UI receives opaque local playback routes.

### Local player server

The local server binds to `127.0.0.1` on an available port and generates a random connection token for each process lifetime. The launcher opens a tokenized bootstrap URL in Edge; the web application exchanges it for an in-memory session and removes it from visible navigation state.

The server exposes a minimal API:

- `GET /api/capabilities`
- `POST /api/session`
- `GET /api/live-courses`
- `POST /api/live-courses/{course_id}/{sub_id}/refresh`
- `GET /media/{course_id}/{sub_id}/{view}/manifest.m3u8`
- `GET /media/segment/{opaque_id}`

Manifest responses are rewritten so every segment returns through the local proxy. Segment identifiers are short-lived, opaque, and scoped to the current local session. The server streams bytes without persisting them.

### Edge extension

The extension uses Manifest V3 and requests access only to the Fudan WebVPN/iCourse origins and the project's Pages origin. Its background worker:

- Detects whether the browser already has a working WebVPN session.
- Opens the official CAS login page when user interaction is required.
- Requests course and current-live metadata using browser-held cookies.
- Rewrites live manifest and segment requests through WebVPN.
- Exposes a small external message protocol to the approved Pages origin.

The extension does not store a UIS password. Its popup offers a compact live-course list and an action to open the full shared player.

For Pages playback, the extension exposes a web-accessible, extension-origin player frame to the approved Pages origin. Pages embeds that frame and sends only course/view commands to it. HLS requests, WebVPN cookies, signed URLs, `MediaSource`, and generated object URLs stay inside the extension-controlled frame rather than crossing into the `github.io` JavaScript context. A proof-of-transport test for Edge extension cookies, manifest loading, and frame embedding is the first acceptance gate for the extension increment.

### Shared web interface

One UI implementation runs in three transport modes:

1. `local`, using the loopback API.
2. `extension`, using external extension messaging.
3. `disconnected`, showing installation and connection guidance.

GitHub Pages starts in capability-detection mode. It prefers the extension-owned player frame and may fall back to the local bridge if Edge grants the required private-network access. The local player serves the same UI directly and always selects local mode.

The Pages site contains no account credentials and no Fudan media URL. Without an installed helper it remains a project landing page, not a media proxy.

## User experience

The live page uses a focused two-pane layout:

- A compact left rail lists current live courses and their time/room context.
- The main area holds the player, course identity, connection state, and view selector.

The visual direction is an academic control desk rather than a generic video site: deep ink-blue surfaces, warm paper accents, restrained status colors, and high-density information with generous player space. Motion is limited to connection-state transitions and a subtle live indicator. The interface remains usable at laptop widths and collapses the course rail into a drawer on narrow screens.

The primary flow is:

1. Start the local player, open the extension, or visit Pages.
2. Establish a local or extension transport.
3. Complete official CAS login if no valid session exists.
4. Load available courses and emphasize current live sessions.
5. Select a course and fetch a fresh source.
6. Begin teacher-view playback near the live edge.
7. Switch view or reconnect without exposing upstream URLs.

## Session and media data flow

### Local mode

```text
Edge UI
  -> loopback API
  -> live core
  -> authenticated WebVPN session
  -> iCourse live metadata

Edge HLS player
  -> loopback manifest route
  -> rewritten loopback segment routes
  -> streaming WebVPN requests
  -> iCourse live media
```

### Extension mode

```text
Extension page or GitHub Pages
  -> extension message protocol
  -> extension background worker
  -> browser WebVPN session
  -> iCourse metadata and media
```

The extension keeps media bytes and extension-owned object URLs inside its embedded player frame. It does not return them, or signed upstream URLs, to the Pages JavaScript context.

## Refresh and recovery

- A media request begins with a fresh source lookup rather than a previously copied URL.
- Transient manifest or segment failures use a small bounded retry budget.
- Repeated failures invalidate the current source and request new live metadata.
- Authentication failures invalidate the WebVPN/iCourse session and transition to an explicit login-required state.
- Automated password submission is never placed in an unbounded retry loop.
- After recovery, playback seeks to the current live edge instead of replaying cached fragments.
- When the platform reports that the session is no longer live, the player stops fetching media and returns to the course list.
- Missing source variants disable only the affected view selector.

## Security and privacy

- Credentials, cookies, authentication tokens, signed media URLs, and opaque segment mappings are redacted from logs and error reports.
- Credentials are read from local environment configuration or entered into the local process and kept in memory. They are not stored by Pages or the extension.
- The loopback API requires a process-lifetime token and validates request origins.
- Media proxy responses prevent caching where practical.
- Extension permissions are narrowed to required Fudan and project origins.
- Continuous integration uses fixtures and fake sessions; it never uses a real student account.
- Public issue templates instruct reporters not to paste logs containing private session data.

## Error states

- **Login required:** Show the official CAS entry action, then retry after the user returns.
- **No live courses:** Show a neutral empty state and a manual refresh action.
- **Source expired:** Refresh metadata automatically and preserve the selected view.
- **Network interruption:** Retry briefly, then distinguish local-network, WebVPN-session, and platform failures.
- **Course ended:** Stop media traffic and mark the session ended without switching to playback content.
- **View unavailable:** Disable that view while keeping other views playable.
- **Local helper unavailable:** Pages offers extension/local-player installation choices.
- **Extension unavailable:** Pages may probe the loopback bridge, then falls back to disconnected guidance.

## Testing strategy

Development follows test-driven changes. Tests use recorded, redacted response shapes and synthetic HLS manifests.

### Unit tests

- Current-live filtering and stable `LiveCourse` mapping.
- Source-variant mapping.
- WebVPN URL conversion.
- HLS manifest rewriting for absolute and relative segment URLs.
- Source-expiry and bounded retry decisions.
- Secret and URL redaction.

### Local integration tests

- Loopback-only binding.
- Bootstrap-token exchange and rejection of invalid tokens.
- Course-list and refresh API contracts.
- Streaming response status, content type, cache headers, cancellation, and cleanup.
- No persistence of media bytes or authentication material.

### Extension tests

- Message schema validation.
- Allowed-origin enforcement.
- Session-state transitions.
- URL rewriting and source refresh.
- Permission-manifest audit.

### Browser verification

- Edge playback of at least two different currently live courses when available.
- Teacher/student view switching when both exist.
- Forced source-expiry recovery.
- Session-expiry login flow.
- GitHub Pages connection through the extension.
- Local player start, stop, and relaunch behavior.

If only one course is live during verification, a second redacted API fixture and synthetic live manifest provide the second-course regression case. A real account is used only for manual local verification and never in CI.

## Build and release

GitHub Actions will:

1. Run Python and JavaScript tests.
2. Audit the extension manifest and packaged file list.
3. Build the Windows local-player artifact.
4. Package the Edge extension as a ZIP for developer-mode installation.
5. Deploy the shared interface and installation documentation to GitHub Pages.
6. Attach versioned artifacts and checksums to GitHub Releases.

The public README will distinguish clearly between the existing lecture-summary subscriber and the new current-live player. Setup instructions will use placeholders and local configuration; no personal configuration is included.

## Delivery order

The work is implemented as three reviewable increments over a shared foundation:

1. Live core and Windows local player.
2. Edge extension and shared transport contract.
3. GitHub Pages integration, packaging, documentation, and release automation.

Each increment must keep existing repository tests green and must satisfy its own security and playback acceptance checks before the next increment begins.
