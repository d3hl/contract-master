# HANDOFF

- Task / issue / plan revision:
- Phase / authoritative owner:
- Orca run / Task / Dispatch / request ID / exact recovery action:
- Workspace / branch / commit:
- Pinned master commit / bundle digest:
- Completed work:
- Verification evidence (command, commit, outcome, artifact):
- Unresolved findings / blockers:
- Exact next action:
- Linear synchronization: queued / delivered / uncertain; outbox identity:

The portable JSON equivalent is `contracts/v1/handoff.schema.json`. The manager
stores it transactionally, exports `.state/handoffs/TASK.json` and enqueues the
Linear update. Recover exports from the database if interrupted. Never treat an
unsynced local HANDOFF as proof that its Linear comment was delivered.
