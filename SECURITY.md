# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest (`main`) | ✅ |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Please report security issues by emailing the maintainer directly or using [GitHub's private vulnerability reporting](https://github.com/AK11105/Inference-Engine/security/advisories/new).

Include:
- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fix (optional)

You can expect an acknowledgement within 48 hours and a resolution or mitigation plan within 14 days.

## Scope

Areas of particular concern for this project:

- API key authentication bypass
- Rate limiting circumvention
- Arbitrary code execution via model loading
- Path traversal in model artifact loading
- Secrets exposure via logs or API responses
