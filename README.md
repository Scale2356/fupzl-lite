# litefupzl

`litefupzl` is a lightweight browser runner for checking that a
cookie-authenticated forum session can log in, pass browser challenges, and
perform human-like read activity.

It does not reply, create topics, or run lottery actions. The only optional
write action is the bounded mutual-like pass described below.

## Features

- Browser challenge prewarm and challenge handling before authenticated work.
- Cookie login proof with authenticated browser-session checks.
- Read-only topic browsing with human-like scrolling and retry behavior.
- Optional mutual-like pass for configured usernames.
- Per-browser `/topics/timings` status diagnostics in redacted logs.
- Optional cookie refresh with validation before writing a GitHub secret.
- Manual and scheduled runs share the same cookie-refresh switch.
- GitHub Actions run cleanup with recent-run retention.
- Artifact upload is disabled by default and must be enabled per manual run.

## Local use

```powershell
python -m pip install -e ".[test]"
python -m pytest -q
```

Create a local `.env.local` when running outside GitHub Actions:

```env
LITEFUPZL_COOKIES_JSON=["_t=<account1_redacted>"]
LITEFUPZL_DURATION_MINUTES=5
LITEFUPZL_HEADLESS=true
LITEFUPZL_BROWSER=chromium
LITEFUPZL_PROXY_SERVER=
LITEFUPZL_VIRTUAL_DISPLAY=true
LITEFUPZL_OUTPUT_DIR=output/litefupzl
LITEFUPZL_COOKIE_REFRESH_ENABLED=true
LITEFUPZL_MUTUAL_LIKE_USERS_JSON=[]
```

Run the main job:

```powershell
python apps/litefupzl/main.py
```

Run diagnostics:

```powershell
python apps/litefupzl/auth_probe.py
python apps/litefupzl/probe_browser.py
python apps/litefupzl/cf_probe.py
```

## Cookie format

`LITEFUPZL_COOKIES_JSON` must be a JSON array of cookie strings:

```json
["_t=<account1_redacted>"]
```

Multiple accounts are supported by adding more cookie strings to the same JSON
array:

```json
[
  "_t=<account1_redacted>",
  "_t=<account2_redacted>",
  "_t=<account3_redacted>"
]
```

Use only the durable login cookie. Do not add short-lived browser/session
cookies such as `_forum_session` or `cf_clearance`.

The main run processes cookie slots sequentially. Each array item is
assigned a public slot alias such as `slot-001`, `slot-002`, and so on. Probe
commands are quick diagnostics and currently use only the first cookie slot.

## GitHub Actions setup

Configure these repository secrets and variables under:

`Settings` → `Secrets and variables` → `Actions`

### Secrets

#### `LITEFUPZL_COOKIES_JSON`

Required. A JSON array of cookie strings used by the browser session.

Single-account example:

```json
["_t=<account1_redacted>"]
```

Multi-account example:

```json
[
  "_t=<account1_redacted>",
  "_t=<account2_redacted>"
]
```

#### `LITEFUPZL_ACTIONS_ADMIN_TOKEN`

Optional. A GitHub token used only when you enable cookie refresh or need
workflow-run cleanup permissions beyond the default workflow token.

Recommended permissions:

- `actions:read`
- `actions:write`
- `secrets:write`

Do not place this token in code, commits, logs, or artifacts.

#### `LITEFUPZL_MUTUAL_LIKE_USERS_JSON`

Optional. A JSON array of usernames for the bounded mutual-like pass.

Example:

```json
["user_a", "user_b", "user_c"]
```

Missing, empty, malformed, or `[]` disables mutual-like entirely.

When enabled, each cookie slot independently:

1. waits until roughly half of that slot's read duration has elapsed;
2. fetches each target user's recent replies and topic first posts from the
   last 30 days;
3. processes candidates from oldest to newest;
4. skips content that is already liked, not likeable, or belongs to the
   current account;
5. sends at most 25 likes total for that slot.

The per-target quota is `floor(25 / username_count)`. For example, three
target usernames allow at most eight likes per target in one slot. If more than
25 usernames are configured, the per-target quota is zero and the pass is
skipped for that slot.

Store this value as a repository secret when possible, because usernames are
treated as sensitive operational data.

### Repository variables

#### `LITEFUPZL_SITE`

Forum host name. Default: `linux.do`.

#### `LITEFUPZL_DURATION_MINUTES`

Default read duration per cookie slot when the manual input is empty. Default:
`40`.

Slots run sequentially, not in parallel. For example, if this is `40` and
`LITEFUPZL_COOKIES_JSON` contains two accounts, the main work can run
for about `40 + 40 = 80` minutes, plus setup, login verification, probes, and
cleanup overhead. Keep the workflow timeout in mind when adding more accounts.

#### `LITEFUPZL_HEADLESS`

Browser headless mode. Use `true` or `false`. Default in Actions: `false`.

#### `LITEFUPZL_BROWSER`

Browser backend to use.

Supported values:

- `chromium`
- `firefox`
- `camoufox`
- `patchright-chromium`

Default in Actions: `chromium`.

#### `LITEFUPZL_PROXY_SERVER`

Proxy URL passed to the browser, for example:

```text
http://127.0.0.1:1080
```

Leave empty for no browser proxy.

#### `LITEFUPZL_VIRTUAL_DISPLAY`

Use a virtual display when running a non-headless browser on Linux. Use `true`
or `false`. Default in Actions: `true`.

#### `LITEFUPZL_OUTPUT_DIR`

Directory for local redacted output files. Default: `output/litefupzl`.

#### `LITEFUPZL_CF_PROBE_URL`

Challenge-probe URL. Set this only to the target you are authorized to test.

#### `LITEFUPZL_CF_PROBE_TIMEOUT_SECONDS`

Maximum challenge handling time for the challenge probe. Default: `120`.

#### `LITEFUPZL_ACTIONS_RUNS_KEEP`

Number of recent workflow runs to keep during cleanup. Default: `15`.

### Local/runtime variable

#### `LITEFUPZL_COOKIE_REFRESH_ENABLED`

Cookie refresh switch for local runs and scheduled GitHub Actions runs. Default:
`true`.

For scheduled GitHub Actions runs, set repository variable
`LITEFUPZL_COOKIE_REFRESH_ENABLED=false` only if you want to disable automatic
validated cookie write-back. Manual runs use the `cookie_refresh_enabled`
workflow input for that single run.

## Manual workflow inputs

### Main run

#### `duration_minutes`

Optional manual runtime override. Leave empty to use
`LITEFUPZL_DURATION_MINUTES`. This value is also per cookie slot.

#### `cookie_refresh_enabled`

Default: `true`. Set to `false` only for a manual run where refreshed cookies
should not be written back to `LITEFUPZL_COOKIES_JSON`.

Scheduled runs do not read this manual input. They use repository variable
`LITEFUPZL_COOKIE_REFRESH_ENABLED` instead.

#### `cookie_refresh_probe`

Set to `true` to run the redacted GitHub secret persistence probe.

#### `upload_artifacts`

Set to `true` to upload redacted debug artifacts for this manual run.

Default: `false`.

### Probe run

#### `probe`

Choose one:

- `auth`: verifies authenticated browser-session access.
- `browser`: runs browser read/timing diagnostics.
- `cf`: runs the configured challenge probe.

#### `upload_artifacts`

Set to `true` to upload redacted debug artifacts for this manual probe run.

Default: `false`.

## Output and logging

Local output files are written under `LITEFUPZL_OUTPUT_DIR`.

Console logs are intentionally coarse-grained and designed to be public-safe:

- raw cookies are redacted;
- usernames are redacted;
- topic ids and topic titles are redacted;
- token values are not printed.

Login verification is shown as a single `login-check` step in console logs.
Detailed login proof events are written only to local output files, which are
uploaded by GitHub Actions only when a manual run sets `upload_artifacts=true`.

Mutual-like console logs show only aggregate state: enabled or skipped, target
count, and total liked count. They do not show usernames, post ids, topic ids,
titles, URLs, or concrete like targets. Per-candidate mutual-like debug records
use aliases such as `target-001` and `candidate-0001` and are written to local
output files only.

For each observed `/topics/timings` request, diagnostics include:

- timestamp;
- slot alias;
- browser backend;
- URL category;
- HTTP status code.

## Cookie refresh behavior

Cookie refresh is enabled by default.

Manual runs use the `cookie_refresh_enabled` workflow input. Scheduled runs use
repository variable `LITEFUPZL_COOKIE_REFRESH_ENABLED`.

When enabled, the runner:

1. extracts refreshed browser cookies from the authenticated context;
2. drops volatile cookies such as `_forum_session` and `cf_clearance`;
3. validates the refreshed cookie in a fresh browser session;
4. writes the validated cookie JSON back to `LITEFUPZL_COOKIES_JSON`.

If validation fails, the secret is not updated.
