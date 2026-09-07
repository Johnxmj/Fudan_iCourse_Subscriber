# Fudan iCourse Subscriber Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the current V2 subscriber fork with the verified Paratera relay, five requested courses, email delivery, GitHub Pages, and an end-to-end smoke test.

**Architecture:** Retain the upstream multi-provider runtime and change only the DeepSeek model identifier. Repository secrets feed GitHub Actions; Actions produce encrypted database shards on the `data` branch; the static Pages frontend reads and decrypts those shards in an ephemeral browser session.

**Tech Stack:** Python 3.12, `unittest`, OpenAI-compatible HTTP API, GitHub Actions, GitHub Pages, Alpine.js, sql.js, Web Crypto API, GitHub CLI.

## Global Constraints

- Do not commit, print, or capture plaintext UIS, SMTP, relay, or GitHub credentials.
- Keep the upstream V2 architecture and default daily schedule.
- Use relay base URL `https://llmapi.paratera.com/v1` and model `DeepSeek-V4-Flash-0731`.
- Configure course IDs `37142,37234,38154,38463,38723`.
- Use the existing QQ sender and Fudan recipient supplied by the user.
- Validate one course before relying on the five-course schedule.

---

### Task 1: Relay model compatibility

**Files:**
- Create: `tests/test_runtime_config.py`
- Modify: `src/runtime/config.py:36-46`

**Interfaces:**
- Consumes: `src.runtime.config.MODEL_PROVIDERS` and `resolve_model_providers()`.
- Produces: a DeepSeek provider that calls `DeepSeek-V4-Flash-0731` at the `DEEPSEEK_BASE_URL` supplied by Actions.

- [ ] **Step 1: Write the failing regression test**

```python
import importlib
import os
import unittest


class RuntimeConfigTest(unittest.TestCase):
    def test_deepseek_relay_model_and_base_url(self):
        os.environ["DEEPSEEK_API_KEY"] = "test-key"
        os.environ["DEEPSEEK_BASE_URL"] = "https://relay.invalid/v1"
        from src.runtime import config
        importlib.reload(config)
        provider = next(p for p in config.resolve_model_providers()
                        if p["name"] == "deepseek")
        self.assertEqual(provider["base_url"], "https://relay.invalid/v1")
        self.assertEqual(provider["models"], ["DeepSeek-V4-Flash-0731"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Verify the test fails against upstream configuration**

Run: `python -m unittest tests.test_runtime_config -v`

Expected: failure showing `deepseek-v4-flash` differs from `DeepSeek-V4-Flash-0731`.

- [ ] **Step 3: Apply the minimal model change**

```python
"models": [
    "DeepSeek-V4-Flash-0731"
],
```

- [ ] **Step 4: Verify configuration and syntax**

Run: `python -m unittest tests.test_runtime_config -v`

Expected: one passing test.

Run: `python -m compileall -q src scripts main.py tests`

Expected: exit code 0 with no output.

- [ ] **Step 5: Commit the compatibility change**

```bash
git add src/runtime/config.py tests/test_runtime_config.py
git commit -m "fix: use Paratera DeepSeek model identifier"
```

### Task 2: Repository configuration and push

**Files:**
- No source files created or modified.
- Remote state: `Johnxmj/Fudan_iCourse_Subscriber` Actions secrets and `main` branch.

**Interfaces:**
- Consumes: the user-authorized UIS, SMTP, course, recipient values and the active CC Switch provider token read directly from `C:\Users\ASUS\.cc-switch\cc-switch.db`.
- Produces: repository secrets `STUID`, `UISPSW`, `COURSE_IDS`, `SMTP_EMAIL`, `SMTP_PASSWORD`, `RECEIVER_EMAIL`, `DEEPSEEK_API_KEY`, and `DEEPSEEK_BASE_URL`.

- [ ] **Step 1: Push the two reviewed local commits**

Run: `git push origin main`

Expected: `main` advances to include the design and relay compatibility commits.

- [ ] **Step 2: Set all eight repository secrets without echoing values**

Use `gh secret set` with each value supplied through process memory or standard input. Read the relay token from the active `Paratera DeepSeek V4 Flash 0731 (0tf3)` row in the local CC Switch SQLite database. Do not write a dotenv file.

- [ ] **Step 3: Verify secret names only**

Run: `gh secret list --repo Johnxmj/Fudan_iCourse_Subscriber`

Expected: all eight required names are present; values remain undisclosed.

- [ ] **Step 4: Re-run the minimal relay request from the configured local provider**

POST a non-sensitive `Reply with exactly: OK` prompt to `https://llmapi.paratera.com/v1/chat/completions` with model `DeepSeek-V4-Flash-0731`.

Expected: HTTP 200 and assistant content `OK`.

### Task 3: GitHub Pages deployment and shell smoke test

**Files:**
- No source files created or modified.
- Remote state: GitHub Pages configuration and `Deploy Frontend` workflow run.

**Interfaces:**
- Consumes: `.github/workflows/deploy-frontend.yml` and `frontend/` from `main`.
- Produces: `https://johnxmj.github.io/Fudan_iCourse_Subscriber/`.

- [ ] **Step 1: Enable Pages with Actions as the build type**

Use the GitHub Pages REST endpoint for `Johnxmj/Fudan_iCourse_Subscriber`, creating or updating the site with `build_type=workflow`.

- [ ] **Step 2: Dispatch the frontend workflow**

Run: `gh workflow run deploy-frontend.yml --repo Johnxmj/Fudan_iCourse_Subscriber -f branch=main`.

- [ ] **Step 3: Wait for the matching workflow run**

Poll the newest `Deploy Frontend` run until it reaches `completed`.

Expected: conclusion `success` and a Pages deployment URL.

- [ ] **Step 4: Smoke-test the deployed shell**

Load the Pages URL in an ephemeral browser context. Verify HTTP 200, title `iCourse Subscriber`, automatic owner/repository detection, visible setup fields, and no uncaught page errors. Close the context afterward so no credentials persist.

### Task 4: Single-course backend and decrypted frontend validation

**Files:**
- No source files created or modified.
- Remote state: `Single Run` workflow and encrypted `data` branch.

**Interfaces:**
- Consumes: repository secrets, course `37142`, and `use_official_transcript=true`.
- Produces: a completed backend smoke run, encrypted database shards, email delivery attempt, and frontend-readable course data.

- [ ] **Step 1: Dispatch a scoped workflow**

Run: `gh workflow run single_run.yml --repo Johnxmj/Fudan_iCourse_Subscriber -f course_ids=37142 -f use_official_transcript=true`.

- [ ] **Step 2: Monitor to a terminal state**

Poll the matching run without printing secret-bearing environment data.

Expected: conclusion `success`. If it fails, inspect failed-step logs and diagnose the failing boundary before changing anything.

- [ ] **Step 3: Verify persisted encrypted data**

Use GitHub API metadata to confirm branch `data`, file `data/icourse-index.enc`, and at least one encrypted shard under `data/shards/`.

- [ ] **Step 4: Validate frontend decryption and data load**

In a fresh ephemeral browser context, supply the repository owner/name, authenticated GitHub token, and UIS credentials. Submit the setup form and wait for the app view to become `courses`.

Expected: no decryption error, at least course `37142` is present, and repository/branch metadata match the deployed fork. Close the context afterward.

- [ ] **Step 5: Verify the scheduled subscription remains complete**

Run: `gh secret list --repo Johnxmj/Fudan_iCourse_Subscriber` and inspect the workflow definition.

Expected: `COURSE_IDS` remains configured for all five courses and `check.yml` retains the upstream default daily schedule.

