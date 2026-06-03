# Obtaining VW EU Data Act OIDC Credentials

This guide walks through registering your application with the Volkswagen EU Data Act portal to obtain the `VW_OIDC_CLIENT_ID` and `VW_OIDC_CLIENT_SECRET` required to run this server.

## Background

Standard VW WeConnect/Carnet mobile API endpoints require cryptographic device attestation (Apple DeviceCheck / Google Play Integrity) and return HTTP 401 for any non-approved client. Vehicle data is instead sourced from the official **EU Data Act portal** operated by Volkswagen Group Info Services AG, which provides an OIDC-compliant identity layer and delivers telemetry as ZIP archives within 15 minutes of a request.

Portal URL: `https://eu-data-act.drivesomethinggreater.com`

Supported brands: VW, Audi, Škoda, SEAT, CUPRA, MAN, Bentley, Elli — across 28 EU countries.

---

## Step 1 — Create a VW ID account

If you don't already have a VW ID (used for the WeConnect app, myAudi, etc.):

1. Go to [https://www.volkswagen.com/en/owners/myvolkswagen.html](https://www.volkswagen.com/en/owners/myvolkswagen.html)
2. Click **Create a VW ID** and complete registration with your email address.
3. Verify your email.
4. Link your vehicle using its VIN in the WeConnect/myVolkswagen app. The vehicle must be linked before the EU Data Act portal will list it.

---

## Step 2 — Register as a data recipient on the EU Data Act portal

1. Go to [https://eu-data-act.drivesomethinggreater.com](https://eu-data-act.drivesomethinggreater.com)
2. Log in with your **VW ID** credentials.
3. Navigate to **Developer / API Access** (the exact menu label may vary — look for "Applications", "API Clients", or "OAuth Clients").
4. Click **Register new application** (or equivalent).
5. Fill in the application details:
   - **Name**: `vag-mcp-chat` (or any descriptive name)
   - **Redirect URI**: Your server's callback URL, e.g. `https://your-domain.example.com/auth/callback`
     - For local development: `http://localhost:8000/auth/callback`
   - **Grant types**: `Authorization Code`
   - **Scopes**: `openid profile email vehicle:read`
6. Submit the registration.

> **Note:** If the portal does not expose a self-service registration UI, look for a contact form or developer support link. VW Group periodically updates the onboarding process.

---

## Step 3 — Retrieve your credentials

After registration you will be shown (or emailed):

| Value | Environment variable |
|---|---|
| Client ID | `VW_OIDC_CLIENT_ID` |
| Client Secret | `VW_OIDC_CLIENT_SECRET` |

Copy these immediately — the client secret is typically shown only once.

---

## Step 4 — Discover the OIDC endpoints

Verify the OIDC well-known document is reachable and note the `authorization_endpoint` and `token_endpoint`:

```bash
curl https://eu-data-act.drivesomethinggreater.com/.well-known/openid-configuration
```

If this path returns 404, try:
```bash
curl https://eu-data-act.drivesomethinggreater.com/oauth/.well-known/openid-configuration
curl https://eu-data-act.drivesomethinggreater.com/oidc/.well-known/openid-configuration
```

The default values in `server/settings.py` assume:
- `VW_OIDC_ISSUER` = `https://eu-data-act.drivesomethinggreater.com`
- Authorize endpoint: `{issuer}/oauth/authorize`
- Token endpoint: `{issuer}/oauth/token`

If the real endpoints differ, override them by setting `VW_OIDC_ISSUER` to the correct base URL or by editing `settings.py` directly.

---

## Step 5 — Configure the server

### Local development

Copy `.env.example` to `.env` and fill in your credentials:

```dotenv
VW_OIDC_CLIENT_ID=your_client_id_here
VW_OIDC_CLIENT_SECRET=your_client_secret_here
VW_CALLBACK_URL=http://localhost:8000/auth/callback
```

Then generate the required crypto keys:

```bash
# MCP JWT signing key
python -c "import secrets; print('MCP_JWT_SECRET=' + secrets.token_hex(32))"

# Fernet encryption key for stored VW tokens
python -c "from cryptography.fernet import Fernet; print('MCP_FERNET_KEY=' + Fernet.generate_key().decode())"
```

### Kubernetes

Update the existing secret with real values:

```bash
kubectl patch secret vag-mcp-chat-secrets -n vag-mcp-chat --type=merge \
  -p "{\"stringData\":{\"VW_OIDC_CLIENT_ID\":\"YOUR_CLIENT_ID\",\"VW_OIDC_CLIENT_SECRET\":\"YOUR_CLIENT_SECRET\"}}"
```

Then restart the deployment:

```bash
kubectl rollout restart deployment/vag-mcp-chat -n vag-mcp-chat
```

---

## Step 6 — Authenticate with your VW ID (first-time setup)

Before vehicle data can be fetched, the server must complete a one-time VW OIDC authentication to obtain and store access/refresh tokens.

### Local

```bash
python -m server.setup
```

The script opens your browser to the VW login page, waits for the OAuth redirect on `localhost:8001`, and saves encrypted tokens to `data/vw_token.enc`.

### Kubernetes (in-cluster)

Run the setup script inside the pod using port-forwarding:

```bash
# Forward the server to localhost
kubectl port-forward -n vag-mcp-chat deployment/vag-mcp-chat 8000:8000 &

# Run setup pointing at the forwarded server
MCP_BASE_URL=http://localhost:8000 python -m server.setup
```

The tokens are written to the pod's NFS-backed PVC at `/app/data/vw_token.enc` and will survive pod restarts.

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `VW_CALLBACK_URL` redirect fails | The redirect URI registered in the portal doesn't match `VW_CALLBACK_URL` exactly (check trailing slash, http vs https) |
| Token exchange returns 400 | `VW_OIDC_CLIENT_SECRET` is wrong or the code has already been consumed |
| Data package never arrives | Vehicle not linked to your VW ID, or VIN not supported by the EU Data Act portal in your country |
| ZIP parses to all `None` fields | Field names in the ZIP differ — run server with `DEBUG` logging, the parser logs the full archive structure |
