---
status: accepted
---

# Use a same-origin proxy for browser authentication

Nebula browser clients call `/api/v1/*` on the frontend origin, which rewrites
to backend `/v1/*`. Refresh tokens remain in `HttpOnly; Secure;
SameSite=Strict` cookies scoped to `/api/v1/auth`, while access tokens remain
in browser memory. This avoids cross-site refresh cookies and limits CSRF
defence to exact configured-Origin checks on every cookie-mutating operation:
verify, refresh, and logout. Every deployed frontend must therefore configure
the same rewrite and must not call the backend host directly from browser code.

Direct cross-site Vercel-to-backend cookies were rejected because they require
weaker `SameSite` settings and a broader credentialed-CORS/CSRF interface.
