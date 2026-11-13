# groupctl 1.1 package review

`groupctl` is a local-first, file-backed collaboration product for software teams in which humans and AI agents work in parallel.

## Included capabilities

- Immutable collaboration event records and schema validation.
- Git-aware status, fetched remote event discovery, and synchronization.
- Structured task assignment and listing.
- Provider-neutral context export and validated event submission.
- Live OpenAI-compatible model requests for implementer, reviewer, and analyst roles.
- Concurrent configured agent execution (up to eight workers) with unique task claims.
- Distinct human-member and AI-agent attribution.
- SHA-256-protected code proposal patch artifacts.
- Human-gated patch application restricted to personal feature branches and exact base commits.
- Publishing committed agent contributions, reviews, testing evidence, integration and synthesis proposals.
- Local HTML dashboard, protocol audit, and human-confirmed finalization.
- A no-API mock agent and a three-member Git collaboration demo.

## Not claimed

This is not a hosted multi-tenant service. It does not provide account authentication, organization-level access control, payment handling, remote worker management, or automatic model installation. Agent IDs are attribution labels, not cryptographic identity. Live model calls require a running compatible endpoint and may consume local compute or paid provider usage. The model's output is not proof of correctness.

Implementer agents do not directly edit files or run arbitrary commands. They return patch proposals. A human inspects and applies a proposal, tests it, commits it, and chooses whether to publish or integrate it.
