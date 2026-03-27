# Issue: SSRF Protection and Custom Endpoint URL Validation

**Labels**: `security`, `critical`, `v10`
**Priority**: CRITICAL

## Problem

### Missing SSRF protection for custom API endpoints
`_validate_base_url()` in `providers/openai_compatible.py` checks URL scheme and hostname but does NOT block:
- Internal metadata service URLs (169.254.169.254 for AWS/GCP)
- Private network addresses (192.168.x.x, 10.x.x.x, 172.16.x.x) unless localhost
- Link-local addresses (169.254.x.x)

### Unprotected HTTP for non-localhost endpoints
Custom provider supports `http://` URLs with no warning for non-localhost external endpoints when an API key IS provided. The warning only fires when BOTH conditions are met: external URL AND no API key. A user providing `http://example.com:8000/v1` with an API key gets no warning about plaintext transmission.

## Key Files

- `providers/openai_compatible.py` (lines 197-250)
- `providers/custom.py` (line 51)

## Proposed Solution

1. Add `ipaddress` module checks to block all private/reserved/loopback IP addresses for non-localhost custom endpoints
2. Always warn when using HTTP for non-localhost URLs, regardless of API key presence
3. Optionally: enforce HTTPS for non-localhost by default with a config override for explicit opt-in

## Related Findings

- Audit Report 06 (Security Reviewer): Findings 2, 5
