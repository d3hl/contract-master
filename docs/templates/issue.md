# Executable issue template

Add human-readable requirements, non-goals, priority and acceptance details above
the machine block. Use actual Linear blocking relations for dependencies; do not
encode a hidden dependency list in prose or grant permissions through this block.
Feature parents are tracking items and need no executable block.

The block below is illustrative. Replace the base SHA with a **real full commit**
and scope/check IDs with registered values. Ordinary incomplete prose remains
unqueued until clarified; no agent invents the missing fields.

```contract-master
{
  "repo_id": "d3hl/contract-master",
  "base_commit": "0000000000000000000000000000000000000000",
  "goal": "Document one verified reusable workflow fact",
  "allowed_scope": ["docs/knowledge"],
  "acceptance_criteria": ["The note includes a reproducible check and primary source link"],
  "required_checks": ["unit"]
}
```

Identity, project, parent kind, status and dependency facts are supplied by current
Linear reads. These fields are forbidden inside the block. The manager resolves
only registered check IDs; issue content cannot introduce command strings.
