# Fudan iCourse Subscriber deployment design

## Goal

Deploy the current upstream V2 application in `Johnxmj/Fudan_iCourse_Subscriber`, use the existing Paratera relay credential for summarization, configure the five requested courses and email delivery, and verify both GitHub Actions and the GitHub Pages frontend without exposing plaintext credentials in commits or logs.

## Selected approach

Keep the upstream provider architecture and make one repository change: replace the DeepSeek provider's default model identifier with the relay-supported `DeepSeek-V4-Flash-0731`. Store the relay URL in `DEEPSEEK_BASE_URL` and its credential in `DEEPSEEK_API_KEY`. This is smaller and easier to maintain than adding a new provider, and it avoids reviving the obsolete pre-V2 fork.

Alternatives rejected:

- Adding a separate `relay` provider would work but adds configuration that duplicates the existing OpenAI-compatible DeepSeek entry.
- Patching the old fork would omit the V2 sharded database, PPT OCR, provider fallback, and frontend.

## Secrets and data flow

Repository secrets provide UIS credentials, subscribed course IDs, SMTP credentials, recipient email, relay key, and relay base URL. The workflow exports only provider variables declared in `MODEL_PROVIDERS`, then removes the aggregate secrets context before launching Python. No plaintext secret is committed.

The backend logs into iCourse through WebVPN, processes selected lectures, calls the relay through OpenAI-compatible `chat.completions`, emails notes, and writes encrypted sharded databases to the `data` branch. The browser frontend reads those encrypted shards through GitHub's API and decrypts them locally from the student's UIS credentials.

## Deployment and validation

1. Add a regression test asserting that the configured relay model identifier is exact and that environment-based provider resolution preserves the custom base URL.
2. Apply the one-line model identifier change and run the focused test plus Python compilation checks.
3. Push the reviewed change to `main`, configure all repository secrets, and enable GitHub Pages with the Actions build type.
4. Dispatch the frontend deployment and verify the public page loads, detects `Johnxmj/Fudan_iCourse_Subscriber`, and shows the setup flow without JavaScript console failures.
5. Dispatch a single-course workflow for course `37142` with official transcripts preferred. If official subtitles are unavailable, the existing pipeline may fall back to ASR. This creates the encrypted `data` branch while limiting the initial validation scope.
6. After the workflow completes, verify its logs for authentication, model, database, and mail success without printing secrets. Then load the deployed frontend with the configured credentials and confirm the course database opens.
7. Leave the scheduled workflow configured for all five requested course IDs at the upstream default schedule.

## Error handling and safety

- Stop before a destructive database reset, force-sync, or deletion not required by the deployment.
- Treat any UIS, SMTP, relay, or Pages failure as a separate boundary and diagnose it from GitHub Actions evidence.
- Do not copy credentials into source files, test fixtures, design documents, command output, or browser screenshots.
- The previously pasted UIS password and SMTP authorization code remain compromised by disclosure; deployment can use them for this requested test, but they must be rotated afterward and the corresponding repository secrets updated.

