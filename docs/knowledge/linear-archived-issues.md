# Linear listing omits archived issues

Observed on Orca 1.4.243, 2026-10-29.

`orca linear list-issues --project <project UUID> --workspace <workspace UUID>`
omits archived issues unless `--include-archived` is passed. In the Contract
Master Automation project the listing without the flag omitted D3S-100
(completed, archived); the flagged listing included it. A full read by identifier,
`orca linear issue D3S-100 --full`, still returns the archived issue completely.
D3S-100 is archived; no statement is made about why it was archived.

## Intake is unaffected

`python3 -m contract_master reconcile` (`Intake` in `contract_master/adapters.py`)
queues only open issues, so an archived (always closed) issue would never be
queued. Dependency status is read by identifier with a full issue read, which
returns archived issues. Omitting archived issues from the listing therefore
cannot hide executable work: an archived issue is always closed, so it can only
ever be a satisfied dependency or settled history.

Use `--include-archived` for history, audits, and counting closed or completed
work through Orca. Do not use the plain listing to count closed work.

## Sources

- [Linear: delete and archive issues](https://linear.app/docs/delete-archive-issues),
  section "Auto-archive": closed issues are archived automatically after the
  team's auto-archive period (6 months here, per the current HANDOFF).
- `orca linear list-issues --help` (1.4.243) lists the `--include-archived`
  option.

## Reproducible read-only check

Compare sets, not fixed counts: counts change as issues open, close, and archive.
Use the project and workspace UUIDs from `config/registry.json`.

```sh
PROJECT=<project UUID>; WORKSPACE=<workspace UUID>
orca linear list-issues --project "$PROJECT" --workspace "$WORKSPACE" --json > /tmp/plain.json
orca linear list-issues --project "$PROJECT" --workspace "$WORKSPACE" --include-archived --json > /tmp/all.json
python3 - /tmp/plain.json /tmp/all.json <<'PY'
import json, sys
def ids(path):
    return {issue["identifier"] for issue in json.load(open(path))["result"]["issues"]}
plain, flagged = ids(sys.argv[1]), ids(sys.argv[2])
print("without:", len(plain), "with:", len(flagged))
print("archived only:", sorted(flagged - plain))
PY
orca linear issue D3S-100 --full --json   # substitute an identifier printed above
```

The first count should be smaller; the identifiers printed as archived only are
absent from the plain listing yet still readable with `orca linear issue --full`.
No Linear write is involved.
