# Security policy

## Supported versions

IslamAI has not published a stable release. Security fixes are prepared only for
the current v0.1 foundation branch; older snapshots are unsupported.

| Version | Supported |
| --- | --- |
| Current unreleased v0.1 foundation | Yes |
| Older snapshots | No |

## Reporting a vulnerability

Do not open a public issue for suspected vulnerabilities, exposed credentials,
prompt-injection bypasses, unsafe citation rendering, or private chat data.

When the repository is public, use GitHub's **Report a vulnerability** private
security-advisory form. Before then, contact the repository owner through a
private channel on their GitHub profile and clearly mark the message as a
security report. Include:

- the affected commit and component;
- reproduction steps or a minimal proof of concept;
- impact and any conditions required for exploitation;
- suggested mitigation, if known; and
- whether credentials or personal data may have been exposed.

Remove API keys, tokens, chat text, and unnecessary religious-source excerpts
from logs and screenshots. Maintainers should acknowledge a usable report within
seven days and coordinate disclosure after a fix is available. Timelines may
vary with severity and maintainer availability.

## Security boundaries

- v0.1 is for one trusted local user and binds to `127.0.0.1`. Do not expose it
  to a LAN or the internet.
- The fixed local user is not network authentication.
- Retrieved text and model output are untrusted content and must remain escaped.
- `.env` contains secrets and must never be committed.
- Questions and retrieved excerpts leave the machine when sent to Gemini.
