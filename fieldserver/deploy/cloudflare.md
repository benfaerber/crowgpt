# Cloudflare rollout for field.crowgpt.org

Owner: Daurian. Audit 2026-11-06. **DNS is still DNS-only. This rollout is not
complete.** Ben performs every Cloudflare dashboard change and the promo deploy.
No GitHub push and no firewall changes are authorized by this rollout.

## Before changing DNS

- Phone audio, spoken notes and video use resumable 256 KiB Content-Range PUTs.
  The dashboard uses 4 MiB chunks. Flask caps each body at 16 MiB. A large total
  recording is not one HTTP request. Cloudflare Free's 100 MB request ceiling
  therefore fits the protocol. No URL change or WIRE_VERSION bump is needed.
- Cloudflare currently documents a 125 s origin read timeout and a 30 s origin
  write timeout. The phone already times each request out at 30 s. The last audio
  PUT hashes the entire file, compresses it to FLAC and verifies decoded samples
  synchronously; video finalization hashes without transcoding. The camera
  defaults to 1080p with no app duration/bitrate cap. Finalization now streams
  file hashes in 1 MiB blocks, so a large video no longer allocates its entire
  file in RAM. Audio conversion still has shared CPU/memory costs.
- Ben's largest realistic capture is ten minutes. On the actual VPS, a temporary
  ten-minute 48 kHz mono WAV assembled from an existing original was 57,600,044
  bytes. Hash/FLAC/verification took 10.522 s at nice 19, producing 15,904,102
  bytes. The original and database were untouched, and the temporary files were
  removed. This is not a phone sync or a test under launch load. The largest
  existing video was 14,400,306 bytes. Still require a ten-minute video/audio
  capture from Pixel 8, including resume and full sync, before launch.
- Caddy 2.6.2 listens on 80/443, Flask on 127.0.0.1:5100. FIELD_TRUST_PROXY=1.
  Trust one sanitized XFF hop from loopback Caddy, then CF-Connecting-IP ONLY if
  that peer is in Cloudflare's published IPv4/IPv6 ranges. Direct origin clients
  keep their socket IP; supplied CF headers cannot choose an allowance. Do not
  add Caddy trusted_proxies or change the explicit XFF overwrite independently.
  Keep Cloudflare Pseudo IPv4 off (or Add Header), and do not enable Remove
  visitor IP headers. Tests cover demo, login and submission buckets.
- The origin's Let's Encrypt certificate expires 2027-01-29. Full (strict) is
  appropriate. TLS-ALPN validation cannot pass through the edge; the supplied
  Caddyfile selects HTTP-01. Port 80 and /.well-known/acme-challenge/ must remain
  reachable without challenges, redirects from custom rules, or cache overrides.
  A valid current certificate is not proof that a future renewal succeeded.
- Cache bypass the entire field hostname. Server responses under /api/ and
  /preview carry private, no-store, including errors and invite pages containing
  the enrollment secret. Do not cache authenticated media or APK responses.
- The newest APK is 107,841,364 bytes (102.85 MiB). The 100 MB upload ceiling
  does not apply to a response download. /preview/<token>/apk is a POST after
  invite validation; retain that path and test it with a legitimate invite.
- Free permits ONE rate rule, IP counting, path matching only, 10 s counting and
  10 s blocking. Match /api/demo/ plus the public /preview/request form in the same rule,
  30 requests per 10 seconds, Block for 10 seconds. This includes menu/poll/clip
  traffic and form submissions, but not phone sync, invites or APK downloads;
  normal polling is once per three seconds. Free cannot add a hostname match.
  Do not replace an existing rule without reviewing what it protects.
- Bot Fight Mode must be OFF: it cannot be skipped for phone routes. Also keep
  Under Attack Mode off. Inspect other managed/custom challenge rules and scope
  them away from field.crowgpt.org. Do not apply Turnstile to phone endpoints.

## Origin and resource isolation: remaining launch risk

The IP 135.148.166.158 is already public. Anyone can bypass Cloudflare using
that IP with the hostname as TLS SNI/Host. Turnstile server verification and
application limits still apply, but edge rate limiting does not. (Since
2026-11-14 the field API runs under waitress with sixteen threads and the
analyze, generate and photo units carry a MemoryMax; CPU is still shared.) Eight waiting demo jobs bounds the
queue, not resource contention. Cloudflare plus Turnstile cannot promise that a
traffic spike will never affect uploads on this shared VPS.

A firewall allowlist for Cloudflare on web ports can prevent ordinary direct
bypass, but it must not restrict SSH. It would break DNS-only clients during DNS
propagation, direct-origin tests/monitoring, and DNS-only rollback until removed.
It also prevents using a DNS-only upload hostname on the same IP. Wrong rules
can lock out access. **Do not apply without Ben's explicit approval.** Keep the
provider console available. Cloudflare ranges need maintenance; authenticated
origin pulls add stronger origin authentication but complicate rollback too.
For stronger isolation, put public demo/access workloads on a separate service
or VPS, or disable live generation during launch. Resource budgets/WSGI service
isolation are still needed before claiming uploads are insulated from load.

## Deployment order (proxy remains grey throughout)

1. Commit and test server changes; run make field-deploy. New verification must
   remain in staging mode (FIELD_DEMO_TURNSTILE_REQUIRED=0) until the new promo
   is deployed and tested. Existing promo buttons continue working in this stage.
2. Install/validate the supplied Caddyfile with a backup, then reload Caddy.
   This changes certificate validation and explicitly preserves the IP contract.
   It does not touch the firewall. Check direct HTTPS/health afterwards.
3. Ben creates a Managed Turnstile widget for crowgpt.org and www.crowgpt.org,
   no pre-clearance. He edits fieldserver/instance/secrets.env on the VPS with
   nvim. Never put the secret in chat, git, command-line arguments or the page.
   The service actually reads instance/service.env; synchronize only the demo
   keys using the deployment helper, without printing secrets, then restart:
   `python3 fieldserver/deploy/sync_demo_secrets.py` followed by
   `sudo systemctl restart crowgpt-field`. The helper preserves other service
   settings and atomically writes a mode-600 service.env. Keep secrets.env
   mode 600 too. These commands run on the VPS; never paste keys into a command.
4. Rebuild/test promo locally. Ben runs make -C promo deploy. New frontend reads
   the public site key from the menu and verifies tokens even in staging mode.
   Confirm a new-page press works. Old open tabs may need refresh after step 5.
5. Enable FIELD_DEMO_TURNSTILE_REQUIRED=1; synchronize service.env and restart.
   Check a tokenless POST is refused and a new-page press still works. Missing
   keys or unavailable verification must fail closed for the demo only.
6. Ben applies the dashboard settings below, reports their values, and confirms.
   Do not flip if the Pixel 8 checks or any upload concern is unresolved.
7. Only then Ben switches field's A record to Proxied. Keep the same IP.

## Dashboard steps (Ben, at the indicated stage)

Turnstile: Account home → Turnstile → Add widget → name CrowGPT public demo →
Add hostnames crowgpt.org and www.crowgpt.org → Managed → pre-clearance No →
Create. Site key is public; secret is pasted only in nvim on the VPS.

On the VPS: `cd ~/crowgpt`, then `nvim fieldserver/instance/secrets.env`.
Add these assignments, replacing placeholders **inside nvim**, never in chat:

```sh
FIELD_TURNSTILE_SITE_KEY=YOUR_SITE_KEY
FIELD_TURNSTILE_SECRET=YOUR_SECRET_KEY
FIELD_DEMO_TURNSTILE_REQUIRED=0
```

Save, run `chmod 600 fieldserver/instance/secrets.env`, and confirm it is ready.
The agent then synchronizes the service configuration and checks staging.
Ben deploys the promo only after that confirmation. Enforcement becomes 1 only
following a successful press from the updated public page.

Zone crowgpt.org → SSL/TLS → Overview → Configure → Full (strict) → Save.
Record the previous mode. Check SSL/TLS → Edge Certificates has an Active
certificate covering field.crowgpt.org.

Zone → Caching → Cache Rules → Create rule → Custom filter expression:
`http.host eq "field.crowgpt.org"` → Cache eligibility: Bypass cache → Deploy.
Place it after any broader matching cache rule so bypass wins. Review old Page
Rules/Workers routes too; none should intercept the field host unexpectedly.

Zone → Security → Settings → Bot Fight Mode: Off; Under Attack Mode: Off.
Inspect Security rules for challenges that could match this hostname. If a
managed rule would challenge phones, scope it away from the field hostname;
never depend on an app solving a challenge. Zone → Network → Pseudo IPv4: Off.
Check Rules → Transform Rules → Managed Transforms: Remove visitor IP headers
must be off. Record prior settings rather than guessing during rollback.

Zone → Security → Security rules (older UI: WAF → Rate limiting rules) → Create
rule → Rate limiting → name CrowGPT demo burst → expression
`(starts_with(http.request.uri.path, "/api/demo/") or http.request.uri.path eq "/preview/request")` → characteristics IP →
30 requests / 10 seconds → Block / 10 seconds → Deploy. If the single Free rule
is already occupied, stop and review it; do not silently replace it.

LAST: Zone → DNS → Records → find A field → Edit → toggle grey DNS-only cloud
to orange Proxied → TTL Auto → Save. Do not edit apex, www or mail records.

## Rollback, written BEFORE the flip

1. DNS → Records → A field → Edit → DNS only → Save (135.148.166.158 unchanged).
   DNS caches may keep using Cloudflare for a while; rollback is not immediate.
2. Disable the new demo rate rule and field cache-bypass rule; restore only the
   other dashboard settings changed in this session to their recorded values.
   Do not restore a known phone-challenging setting while traffic still proxies.
3. Keep the valid Let's Encrypt certificate and HTTP-01 configuration; both work
   DNS-only. If reverting Caddy, validate and reload the saved Caddyfile backup.
   The new IP middleware supports both paths throughout DNS propagation.
4. If demo verification is the problem, hide its buttons/disable the demo until
   fixed. Temporarily restoring REQUIRED=0 reopens the old public endpoint and
   is an explicit security rollback, not a fix. Ben restores promo if needed.
5. No firewall change is part of this rollout. If a separately approved allowlist
   was added, remove it before expecting DNS-only access or rollback to work.

## Verification ledger

Completed: source audit; read-only live Caddy/unit/listener/certificate checks;
actual APK size; ten-minute audio finalization benchmark. Local tests cover
spoofed headers, separate client budgets and no-store. No DNS changes made.

Completed: middleware and staged Turnstile deployed; all four application units
and Caddy healthy; direct HTTPS health carries no-store; streaming-hash fix deployed; Caddy
HTTP-01 configuration validated and reloaded with a backup at
/etc/caddy/Caddyfile.before-cloudflare-20261106. The actual deployed Caddy binary
passed a local end-to-end spoofed-header test. The full server suite passed
895 tests; the subsequent streaming hash change passed 46 upload/storage tests.
Six Chrome tests passed for
widget/API outages, expiry, single-use tokens and rate refusal. A live direct-origin probe with forged CF/XFF headers was refused (503,
verification not configured) and logged the actual client egress IP, not either
forged address. Public promo is built locally, NOT deployed. Pixel 8 is connected but still uses the old LAN URL;
its migration/re-enrollment needs Ben’s confirmation. Pixel 10 is untouched.

Pending: required Turnstile; public promo deployment; dashboard state review; proxy flip; CF-Ray
and cache headers on health; make field-status; test request's real IP in logs;
valid and over-limit demo presses; request-access submission from crowgpt.org;
legitimate invite and full APK download; full Pixel 8 sync including a largest
realistic video/audio capture; certificate renewal through the edge. Pixel 10
must not be used for these tests. Keep launch blocker open until verified.

Sources checked 2026-11-06:
- https://developers.cloudflare.com/support/troubleshooting/http-status-codes/4xx-client-error/error-413/
- https://developers.cloudflare.com/fundamentals/reference/connection-limits/
- https://developers.cloudflare.com/waf/rate-limiting-rules/
- https://developers.cloudflare.com/bots/get-started/bot-fight-mode/
- https://developers.cloudflare.com/turnstile/get-started/server-side-validation/
- https://www.cloudflare.com/ips-v4/ and https://www.cloudflare.com/ips-v6/
- https://caddyserver.com/docs/caddyfile/directives/reverse_proxy
- https://caddyserver.com/docs/automatic-https
- https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/
