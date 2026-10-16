# Web sign-in for the Chrome extension

## Goal

Sign in to the O1 web app. Then connect the O4 Chrome extension to the same account.

## Flow

1. Open the extension. Select **Continue with WCM**.
2. The extension opens the O1 web app. Sign in there if necessary.
3. O1 checks the user's `chrome_extension` grant. O1 makes a code that expires after 60 seconds.
4. The web page sends the code to the installed extension. The extension sends it to the O4 backend.
5. O4 checks the code, extension ID, request state, proof, and current grant. O4 gives the extension its own session.
6. The extension uses that session for O4 API calls. It refreshes the session when necessary.

## Security and data

O1 keeps its sign-in cookies in the web app. The extension never receives the web password or cookies.

Allow only known extension IDs. Use one shared secret on the two backends. Keep this secret out of browser code.

Store only hashes of O4 session tokens in the database. Store browser tokens in Chrome session storage. A code works once.

O1 owns user accounts and access grants. O4 reads the shared `public.profiles` table. O4 stores its sessions in the `extension` schema.

## Rollout

1. Set the same `EXTENSION_HANDOFF_SECRET` on both backends.
2. Set the installed Chrome extension ID in `EXTENSION_ALLOWED_IDS` on both backends.
3. Run the O4 database migration. Start O1 on port 8000 and O4 on port 8001 for local use.
4. Start the O1 web app. Build and reload the extension.
5. Test sign-in, refresh, sign-out, code reuse, and access revocation.

The old O4 password endpoints remain during the rollout. The live extension uses web sign-in.
