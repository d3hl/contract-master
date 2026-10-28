"""Task phases, where each operation may run, and the only legal phase changes."""
from .contracts import ContractError

ACTIVE = ("planning", "ready", "implementing", "verifying", "rework", "awaiting_review")
SETTLED = ("done", "escalated", "superseded")
ALL = ACTIVE + SETTLED

# Phases each trusted manager operation may run in.
OPERATIONS = {
    "pin_context": ("planning",),
    "record_plan": ("planning",),
    "prepare_dispatch": ("ready", "rework"),
    "implementation": ("implementing",),
    "verify": ("verifying",),
    # Not rework: new work there must go through prepare_dispatch so the attempt cap holds.
    "observe_head": ("verifying", "awaiting_review"),
    # The PR can open once there is an output commit; Codex verifies the commit, not the PR.
    "open_pr": ("verifying", "awaiting_review"),
    "codex_merge": ("awaiting_review",),
    "confirm_merge": ("awaiting_review",),
    "complete": ("awaiting_review",),
    "release": ("done", "escalated"),
    "supersede": ACTIVE,
    # Recovery records must be accepted in any phase while ownership exists.
    "handoff": ALL,
    "record_orca_receipt": ALL,
}

# Legal phase changes. Settled phases have no exits.
TRANSITIONS = {
    "planning": ("ready", "superseded"),
    "ready": ("implementing", "superseded"),
    "implementing": ("verifying", "superseded"),
    "verifying": ("verifying", "awaiting_review", "rework", "escalated", "superseded"),
    "rework": ("implementing", "superseded"),
    "awaiting_review": ("verifying", "done", "superseded"),
    "done": (),
    "escalated": (),
    "superseded": (),
}


def check(operation, phase):
    if phase not in OPERATIONS[operation]:
        raise ContractError("Invalid phase: " + phase)


def advance(task, target):
    if target not in TRANSITIONS[task["phase"]]:
        raise ContractError("Illegal phase change: " + task["phase"] + " -> " + target)
    task["phase"] = target
