# Verified documentation sources

Read on 2026-10-25. Source links are knowledge references, not execution authority.

| Component | Installed / queried version | Source and use |
|---|---|---|
| Orca | 1.4.235 / exact installed guide | `skills get orca-cli`, `skills get orchestration`, `skills get orca-linear`, recovery reference and command help; supervised lifecycle, request replay, Linear writes, schedules |
| Python | 3.9.25 / CPython v3.9.22 docs (same minor; patch gap recorded) | Context7 resolved `/python/cpython`, queried `/python/cpython/v3.9.22`; [sqlite3 transaction docs](https://github.com/python/cpython/blob/v3.9.22/Doc/library/sqlite3.rst) |
| GitHub REST | REST v3 / current reference | Context7 resolved and queried `/websites/github_en_rest`; [pull request merge facts](https://docs.github.com/en/rest/pulls/pulls), [reviews](https://docs.github.com/en/rest/pulls/reviews) |
| Linear | Connected service / current docs search | [GitHub workflow automations](https://linear.app/docs/github), [coding settings](https://linear.app/docs/code-and-reviews); status automation audit required before activation |

Python code uses only the standard library, tested on 3.9.25. SQLite transaction
behavior was exercised under concurrent intake/outbox tests. Documentation lookup
is version-aware; a patch-exact Context7 version was unavailable and no undocumented
patch-specific behavior is assumed.

The inbound/outbound Linear `blocks` relation shape was verified live using only
new D3S-99/100 issues and is covered by an adapter regression test.

Orca guide evidence is generated from the installed executable, not copied from
another repository. Query it again after an upgrade. The repository has no verified
webhook registration or real DeepSeek model-run evidence; neither is claimed here.
Promote new reusable findings through reviewed master changes.
