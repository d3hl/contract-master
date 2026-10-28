# Contract Master directory

This repository owns shared automation contracts and operational knowledge. Product code,
tests, architecture and product API contracts belong to their owning repositories.

Read these documents explicitly before work; links alone do not load context:

- [Workflow and ownership](docs/policies/workflow.md)
- [Portable contracts](docs/contracts/v1.md) and [schemas](contracts/v1/)
- [Registry and onboarding](docs/onboarding/repositories.md)
- [Orca coordination and recovery](docs/operations/orca.md)
- [Security and context](docs/policies/context-and-security.md)
- [Pilot and activation gates](docs/operations/pilot.md)
- [Current HANDOFF](docs/operations/HANDOFF.md)

Use Linear for requirements, plans, progress and HANDOFF. The manager is the only
Linear workflow writer. Orca is the only scheduler and coordinator. Claude
investigates, designs, plans and decides completion; DeepSeek implements and tests;
Codex independently verifies, reviews and merges; humans handle escalations.
Never mark Done before Codex merge and final Claude confirmation. Maximum two
implementation attempts. Preserve unknown worker ownership across interruption.

Run `python3 -m unittest discover -s tests -v`. Keep secrets in 1Password; never commit
credentials or send confidential project data to Mem0. Use Bash/zsh on Linux and
PowerShell 7 on Windows. No live workers, deployment, credential provisioning or
merging during initial implementation. Detailed rules live in the linked documents.
