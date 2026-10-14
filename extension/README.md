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
| `WXT_GHL_HOST` | White-labeled GHL host, no protocol (e.g. `app.example.com`) |
| `WXT_API_BASE_URL` | O4 backend base URL, no trailing slash |
| `WXT_API_MOCK` | `true` = answer every API call from in-memory mock data |

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

## Load unpacked / release

```bash
npm run build  # .output/chrome-mv3  — chrome://extensions → Developer mode → Load unpacked
npm run size   # fails if sidepanel JS > 250 KB or background > 40 KB gzipped
npm run zip    # release zip for the Chrome Web Store (private listing)
```

## Checks

```bash
npm run check      # biome
npm run typecheck  # tsc --noEmit
npm test           # vitest run
```
