# Isolated runner capability fixture

The user explicitly authorized this live capability check after bootstrap.
Only `runner_probe/tags.py` may change in the implementation commit. Tests and
requirements are coordinator-owned. Write the structured result only under
`.state/probe-result.json` (ignored). Do not change product code or global config,
read credentials, send Linear updates, push, merge, deploy or launch other agents.
Read `.state/probe-plan.json` and the supplied portable schema before work.
The coordinator owns verification. Obey the live Orca lifecycle preamble.
