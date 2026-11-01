# Security and research data

## Reporting a vulnerability

For sensitive reports, use the repository's **Security → Advisories → Report a vulnerability** option when available. If private reporting is unavailable, open an issue requesting a private contact without including exploit details, credentials, or unpublished data.

Include affected commit/version, reproduction steps using synthetic data, and the expected impact. Do not include live API keys or subscription documents.

## Local configuration

- Store API credentials in process environment variables or a private `.env` file. The example configuration contains empty values.
- Unpaywall contact transmission is opt-in. Configure `CHEM_MAT_HUB_UNPAYWALL_EMAIL` only for an address you authorize sending to that provider.
- Database queries send search terms and applicable credentials to external providers. Local execution does not mean offline execution.
- Keep research-library records, PDFs, extraction evidence, and unpublished notes outside version control.
- Treat downloaded PDFs and extracted text as untrusted input. Keep dependencies updated and avoid exposing local workflows as public services.

No hosted web application or HTTP API is distributed with this project.
