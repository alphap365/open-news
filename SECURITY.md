# 🔐 Security Policy

Open News is a library and set of interfaces for fetching, extracting, and
processing news content. It makes outbound HTTP requests, parses untrusted
HTML/XML/JSON, and can optionally render pages in a headless browser. This
document describes what counts as a security issue, how to report one, and
what is explicitly out of scope.

---

## 📌 Supported versions

| Version | Status |
|---|---|
| `1.0.x` | ✅ Supported |
| `0.x` | ❌ End of life |

Security fixes are issued against the latest `1.0.x` release. If you're on a
pre-release (`1.0.3a*`, `1.0.3b*`), please reproduce on the corresponding
stable release before reporting.

---

## 📣 Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Use GitHub's private vulnerability reporting:

> **Repository → Security → Report a vulnerability**
> https://github.com/alphap365/open-news/security/advisories/new

If you can't use that channel, email **arajitpaul2010@gmail.com** with
`[SECURITY]` in the subject line.

### What to include

- A short description of the issue and its impact.
- Reproduction steps — the smallest script or CLI invocation that
  demonstrates the problem.
- The affected version (`open-news --version`) and Python version.
- Whether the issue requires attacker-controlled input (e.g. a malicious
  feed URL, a hostile article page) or is exploitable without it.
- Any suggested fix, if you have one.

Please **do not** include real credentials, private URLs, or third-party
personal data in the report.

### What to expect

| Stage | Target |
|---|---|
| Acknowledgement of your report | within 3 business days |
| Initial assessment and severity | within 7 business days |
| Fix or mitigation plan | within 30 days for high/critical issues |
| Public disclosure | coordinated with you after a fix ships |

Reporters are credited in the release notes unless they ask not to be.

---

## 🎯 In scope

The following are treated as security issues:

- **Remote code execution** from parsing untrusted content — e.g. a crafted
  HTML/XML/JSON-LD response that causes `lxml`, `feedparser`, or a
  JS-rendering path to execute code.
- **Path traversal or arbitrary file write** — e.g. an article URL or feed
  response that makes `export.to_markdown(path=...)` write outside the
  intended directory.
- **SSRF via proxy or redirect handling** in `httpx_compat.make_client` that
  bypasses caller expectations.
- **Denial of service with trivial cost** — a small, crafted response that
  causes unbounded memory or CPU growth in an extraction or parsing path
  (a huge normal article is not a DoS).
- **Credential or environment leakage** — e.g. proxy credentials or API
  tokens appearing in logs, exceptions, or exported JSON.
- **Dependency confusion or typosquatting** in the declared package
  dependencies.
- **Bypass of the `robots.txt` respect check** in the crawler when
  `obey_robots=True`.

---

## 🚫 Out of scope

- **Content correctness.** If a page extracts the wrong title, wrong author,
  or wrong publish date, that is a bug — please file a normal issue.
- **Aggregator source misattribution.** Source resolution is explicitly
  best-effort and documented as such; wrong `source` values are expected
  behavior, not a vulnerability. See `docs/architecture.md`.
- **Third-party site behavior.** A news site serving different content to
  different User-Agents, or blocking the library's requests, is not a
  security issue in Open News.
- **Rate-limit responses** (HTTP 429, DDG's 202). These are handled; a
  backoff that doesn't suit your use case is a feature request.
- **Playwright/Chromium vulnerabilities.** Report those upstream. If a
  Chromium CVE affects Open News's default flags, mention it and we'll
  document a workaround.
- **Missing hardening with no demonstrated exploit** — e.g. "you should
  also disable X." Reports need a concrete scenario.
- **Anything requiring the attacker to already control the user's shell,
  environment, or Python installation.** Open News is not a sandbox.

---

## 🛡️ Threat model

Open News assumes the following:

| Assumption | Implication |
|---|---|
| Article URLs and feed URLs may be attacker-controlled | Parsers must be robust against hostile HTML/XML/JSON |
| Remote servers are untrusted | No automatic execution of fetched content outside the optional JS renderer |
| Local environment is trusted | No privilege separation between library and caller |
| No secrets are stored by the library | Config file (`~/.config/open-news/config.json`) holds preferences only |
| The optional JS renderer is sandboxed by Playwright | Open News does not add sandboxing on top |

### What the library does **not** do

- It does **not** execute JavaScript from fetched pages unless `js=True` is
  explicitly passed.
- It does **not** follow redirects into non-HTTP schemes.
- It does **not** write to disk except when you pass `path=` to an export
  function, `--save`, or `--export-*`.
- It does **not** read the config file unless the CLI is invoked.
- It does **not** send telemetry.

### What the library **does** do that is worth knowing

- Fetches arbitrary URLs you provide, including redirects, at HTTP and
  (optionally) HTTPS.
- Parses responses with `lxml`, `feedparser`, and `BeautifulSoup` — all
  commonly used, all historically vulnerable to crafted input. Open News
  pins conservative version bounds in `pyproject.toml`.
- Runs a headless Chromium instance when `js=True`. That Chromium will
  execute page scripts and can reach the network. Treat `js=True` on
  untrusted URLs as equivalent to visiting the page in a browser.
- Respects `robots.txt` by default when crawling (`obey_robots=True`), but
  `fetch()` and `search()` do not — they query public news aggregators as a
  normal client would.

---

## 🧰 Safe defaults

Open News ships with the following defaults on purpose:

| Behavior | Default | Change it if |
|---|---|---|
| JavaScript rendering | Off | You trust the URL and need client-rendered content |
| Full-content extraction | Off | You accept the additional network cost |
| Fuzzy title dedupe | On for search/fetch | You need every near-duplicate |
| Crawler `robots.txt` check | On | You own the target site |
| Disk writes | Only on explicit `path=` / `--save` | Never |

If you're building on Open News and expose it to end-user-supplied URLs,
review the threat model above before enabling `js=True`.

---

## 📦 Supply chain

- Open News is published to PyPI as **`open-news-api`**.
- The only official source repository is
  https://github.com/alphap365/open-news.
- Runtime dependencies are pinned to conservative version floors in
  `pyproject.toml`. Optional extras (`js`, `nlp`) are opt-in.
- Builds are reproducible from a clean checkout with `uv sync` or
  `pip install -e ".[dev]"`.
- If you see the package name on a registry other than PyPI, treat it as
  unaffiliated until verified.

---

## 🔄 Revisions

This policy may be updated as the project evolves. Substantive changes are
noted in `docs/changelog.md`.