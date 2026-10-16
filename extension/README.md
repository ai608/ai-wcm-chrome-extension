# WCM Sales Assistant (Chrome extension)

Side-panel call script, history and research for WCM SDRs inside our GoHighLevel
"WCM Sales" sub-account. The panel never talks to GHL or holds a GHL token — it
messages the background service worker, which calls the O4 backend.

## Setup

```bash
cd extension
cp .env.example .env
npm install
npm run dev   # opens Chrome with the extension loaded
```

### Env vars (`.env`, see `.env.example`)

| Var | Meaning |
| --- | --- |
| `WXT_GHL_HOST` | White-labeled GHL host, no protocol (`app.practiceflow.md`) |
| `WXT_API_BASE_URL` | O4 backend base URL, no trailing slash |
| `WXT_O1_WEB_URL` | O1 web app URL for account sign-in |
| `WXT_API_MOCK` | `true` = answer every API call from in-memory mock data |

## Live sign-in (`WXT_API_MOCK=false`)

Start O1's backend on port 8000, O4's backend on port 8001, and O1's frontend on port 5173. Set the same `EXTENSION_HANDOFF_SECRET` on both backends. Add this installed extension's ID to `EXTENSION_ALLOWED_IDS` on both backends.

Open the extension and select **Continue with WCM**. Sign in on O1 if needed. O1 checks the `chrome_extension` grant and connects the extension. The extension receives its own session; O1's web cookies stay in the web app. The O4 backend applies the session-table migration on startup.

## Mock mode (`WXT_API_MOCK=true`)

No backend needed. Any email + password `demo` signs in; password `totp`
triggers the 6-digit flow (code `123456`). The mock location id is
`MOCK_LOCATION`, so a URL like this opens a fixture contact:

```
https://<WXT_GHL_HOST>/v2/location/MOCK_LOCATION/contacts/detail/c_glow
```

| Contact | Scenario |
| --- | --- |
| `c_glow` | Enriched med spa, script ready, history with brief + opportunity |
| `c_vital` | Not enriched — exercises the enrich flow |
| `c_peak` | Script generating (~5 s) then ready; abandoned opportunity |
| `c_fail` | Script failed; `annual_revenue` PATCH always 422 |
| anything else | 404 contact-not-found |

## Research Mode

The side panel is enabled on every tab. On a GHL contact it shows Call Mode; on any other
`http(s)` website it shows **Research Mode** (a website + local visibility audit). Audits only run
when you click **Run audit** / **Run research** / **Re-run** or an on-demand check. The extension
never reads page content — the O4 backend crawls the site.

In mock mode, open one of these sites and click **Run audit** (sections fill in over ~6 s):

| Site | Scenario |
| --- | --- |
| `glowaesthetics.com` | Strong site, grade B (78), GBP matched, Boulevard booking |
| any other (e.g. `example.com`) | Weak site, grade F (32), provisional (no GBP match), 0 city pages |
| `fail.example` | Site section fails, audit ends `partial` |
| `blocked.example` | `url_not_allowed` ("This address can't be audited") |

Other mock behaviour: on-demand checks (domain overview, local competitors, AI visibility) run for
2–4 s; send-report to `bounce@…` is rejected; the Call Mode **Research** tab shows `c_glow` (ready),
`c_peak` (run on demand) and `c_vital` (no website). **Generate prospect report (PDF)** opens
`report.html` in a new tab — use **Save as PDF** there.

`npm run size` budgets (gzipped): side panel (incl. lazy/shared chunks) ≤ 300 KB, background ≤ 40 KB,
report page own chunks ≤ 60 KB.

## Load unpacked / release

```bash
npm run build  # .output/chrome-mv3  — chrome://extensions → Developer mode → Load unpacked
npm run size   # fails if sidepanel JS > 250 KB or background > 40 KB gzipped
npm run zip    # release zip for the Chrome Web Store (private listing)
```

Release packaging requires deployed HTTPS values for `WXT_API_BASE_URL` and `WXT_O1_WEB_URL`, plus `WXT_API_MOCK=false`. It fails if either URL points to localhost.

## Checks

```bash
npm run check      # biome
npm run typecheck  # tsc --noEmit
npm test           # vitest run
```
