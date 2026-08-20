# Mindclade domain portfolio

- `mindclade.com`: company identity, employee email, trust, legal, careers, and status.
- `mindclade.ai`: production product, API, application, console, and authentication.
- `mindclade.dev`: developer documentation, SDKs, schemas, and examples.
- `mindclade.studio`: isolated demos, playgrounds, and experimental experiences.

Squarespace remains the registrar. Google Cloud DNS is the intended authoritative provider. Zone creation and registrar delegation are separate reviewed changes. Production apex records remain Terraform-owned; ExternalDNS may manage only explicitly delegated non-production subzones. DNSSEC is enabled only after nameserver migration is verified and the corresponding DS records are installed at the registrar.
