# Security Policy

## Supported versions

Yazıt is pre-1.0; security fixes land on the latest `0.1.x` release.

| Version | Supported |
| ------- | --------- |
| 0.1.x   | ✅        |
| < 0.1   | ❌        |

## Reporting a vulnerability

Please report suspected vulnerabilities **privately** — do not open a public issue
for a security problem.

- Use GitHub's [private vulnerability reporting](https://github.com/htahaozlu/yazit/security/advisories/new)
  ("Report a vulnerability" under the repository's *Security* tab), or
- Contact the repository owner **@htahaozlu** directly.

Please include: the affected version, your OS/architecture, the backend in use, a
minimal reproduction (the exact command), and the impact you observed. We aim to
acknowledge a report within a few days and to coordinate a fix and disclosure
timeline with you.

## Threat model & scope

Yazıt is a **local** tool. It is the right lens for triaging reports:

- The core engine reads media files and writes transcripts/checkpoints on the local
  filesystem. It performs **no network egress** on its own.
- Network access happens **only** through optional extras you install and invoke:
  - `[url]` downloads media via **yt-dlp** from a URL you provide.
  - `[drive]` talks to the **Google Drive API** with credentials you supply.
  - Installing any backend downloads model weights from their model hub.
- The `[web]` UI binds to `127.0.0.1` by default. It is intended for local,
  single-user use; **do not expose it to an untrusted network** without your own
  authentication/proxy in front of it.
- `ffmpeg` (required) and `yt-dlp` (`[url]`) are external programs Yazıt invokes;
  keep them updated, as their own advisories apply.

In scope: path traversal, unsafe file handling, command/argument injection,
checkpoint corruption that could lose user data. Out of scope: vulnerabilities in
third-party model weights, ffmpeg, yt-dlp, or PyTorch themselves (report those
upstream), and issues that require an already-compromised local machine.
