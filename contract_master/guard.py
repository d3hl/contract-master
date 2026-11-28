"""PreToolUse guard for coordinator turns: Claude plans, DeepSeek implements, Codex merges.

Loaded for every session by the shared `.claude/settings.json`, but it acts only while a
coordinator turn holds a live turn lease (`turn-start` .. `turn-end`); otherwise every call
passes, so person-led contract-master changes keep working. Orca refuses `--settings` in a
Claude automation's extra arguments, so the lease is how a hook knows a turn is running.
An unreadable manager database counts as no turn: `turn-start` would fail on it too.

Reads one Claude Code hook event on stdin. Exit 2 blocks the tool call and the stderr reason
goes back to Claude. During a turn it fails closed on input it cannot read. It is a guard rail
for an honest agent, not a sandbox: it checks plain commands.
"""
import json
import os
import shlex
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / ".state/manager.sqlite3"
DATABASE_ENV = "CONTRACT_MASTER_GUARD_DATABASE"
EDIT_TOOLS = {"Edit", "MultiEdit", "Write", "NotebookEdit"}
AGENT_TOOLS = {"Agent", "Task"}
READ_ONLY_AGENTS = {"Explore", "Plan", "claude-code-guide", "web-fetch"}
SEPARATORS = {"&&", "||", ";", "|", "&", "|&", "(", ")"}
GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
HANDOFF = ("Coordinator turns hand implementation and testing to DeepSeek through Orca and "
           "verification and merge to Codex; Claude does not do them itself.")


def allowed_runners(root=ROOT):
    """(environment, agent) pairs of the enabled DeepSeek runners the registry references."""
    paths = set()
    _collect_runner_configs(json.loads((root / "config/registry.json").read_text()), paths)
    pairs = set()
    for relative in sorted(paths):
        runner = json.loads((root / relative).read_text())
        if runner.get("enabled") is True and runner.get("role") == "deepseek" \
                and runner.get("environment") and runner.get("agent"):
            pairs.add((runner["environment"], runner["agent"]))
    return pairs


def _collect_runner_configs(node, paths):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "runner_config" and isinstance(value, str):
                paths.add(value)
            else:
                _collect_runner_configs(value, paths)
    elif isinstance(node, list):
        for value in node:
            _collect_runner_configs(value, paths)


def turn_active(database=None, clock=time.time):
    """True while a coordinator turn holds an unexpired lease in the manager database."""
    path = Path(database or os.environ.get(DATABASE_ENV) or DATABASE)
    if not path.is_file():
        return False
    try:
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
        try:
            row = connection.execute("SELECT expires FROM turn_lease WHERE id=1").fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        return False
    return bool(row) and row[0] > clock()


def check(event, root=ROOT):
    """Return the reason to block this tool call during a turn, or None to let it run."""
    tool = event.get("tool_name")
    tool_input = event.get("tool_input") or {}
    if tool in AGENT_TOOLS:
        kind = tool_input.get("subagent_type") or "general-purpose"
        if kind in READ_ONLY_AGENTS:
            return None
        return ("Blocked a " + kind + " subagent: only read-only subagents (" + ", ".join(sorted(READ_ONLY_AGENTS))
                + ") run in a coordinator turn. " + HANDOFF)
    if tool in EDIT_TOOLS:
        return _check_edit(tool_input.get("file_path") or tool_input.get("notebook_path"), event.get("cwd"))
    if tool == "Bash":
        return _check_command(tool_input.get("command") or "", root)
    return None


def _check_edit(path, cwd):
    if not path:
        return "Blocked an edit without a file path. " + HANDOFF
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = Path(cwd or ".") / target
    target = target.resolve()
    roots = {Path(tempfile.gettempdir()).resolve()}
    if Path("/tmp").is_dir():
        roots.add(Path("/tmp").resolve())
    for allowed in roots:
        try:
            target.relative_to(allowed)
            return None
        except ValueError:
            continue
    return ("Blocked edit of " + str(target) + ". " + HANDOFF + " Write spec, body and report files under "
            + str(sorted(roots)[0]) + " instead.")


def segments(command):
    """Split a shell command into simple commands (lists of words). Raises ValueError if unparsable."""
    # Lex the whole command so quote state carries across lines; an unquoted newline ends a command.
    lexer = shlex.shlex(command.replace("\\\n", " "), posix=True, punctuation_chars="();<>|&\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    result, current = [], []
    for token in lexer:
        if token in SEPARATORS or (token and set(token) <= set("();<>|&\n") and "\n" in token):
            if current:
                result.append(current)
            current = []
        else:
            current.append(token)
    if current:
        result.append(current)
    return result


def _check_command(command, root):
    try:
        parts = segments(command)
    except ValueError:
        if "worker-start" in command or "git" in command or "gh " in command:
            return "Blocked a command the coordinator guard cannot parse. Rewrite it as plain commands."
        return None
    for words in parts:
        reason = _check_words(words, root)
        if reason:
            return reason
    return None


def _check_words(words, root):
    program = _program(words)
    if program == "git" and _git_subcommand(words) in ("commit", "push"):
        return "Blocked git " + _git_subcommand(words) + ". " + HANDOFF
    if program == "gh" and _after(words, "gh")[:2] == ["pr", "merge"]:
        return "Blocked gh pr merge: only Codex merges, through codex-merge or review-merge."
    for name in ("--agent", "--provider"):
        value = _flag(words, name)
        if value and value.lower().startswith("claude"):
            return "Blocked " + name + " " + value + ": Claude does not hand work to Claude. " + HANDOFF
    if _is_worker_start(words):
        return _check_worker_start(words, root)
    return None


def _is_worker_start(words):
    """True for an Orca `orchestration worker-start` launch, not a search term or echoed text."""
    return any(first == "orchestration" and second == "worker-start" for first, second in zip(words, words[1:]))


def _check_worker_start(words, root):
    try:
        runners = allowed_runners(root)
    except (OSError, ValueError) as error:
        return "Blocked worker-start: cannot read the runner registry (" + str(error) + ")."
    pair = (_flag(words, "--on"), _flag(words, "--agent"))
    if pair in runners:
        return None
    wanted = ", ".join("--on " + env + " --agent " + agent for env, agent in sorted(runners)) or "none enabled"
    return ("Blocked worker-start with --on " + str(pair[0]) + " --agent " + str(pair[1])
            + ": implementation workers must be a registered DeepSeek runner (" + wanted + "). "
            + "The start never reached Orca, so no Dispatch exists; fix the flags and run it once.")


def _program(words):
    for word in words:
        if "=" in word and not word.startswith(("-", "/", ".")) and word.split("=", 1)[0].isidentifier():
            continue
        return Path(word).name
    return None


def _after(words, program):
    for index, word in enumerate(words):
        if Path(word).name == program:
            return words[index + 1:]
    return []


def _git_subcommand(words):
    rest = _after(words, "git")
    index = 0
    while index < len(rest):
        word = rest[index]
        if word in GIT_OPTIONS_WITH_VALUE:
            index += 2
        elif word.startswith("-"):
            index += 1
        else:
            return word
    return None


def _flag(words, name):
    for index, word in enumerate(words):
        if word == name and index + 1 < len(words):
            return words[index + 1]
        if word.startswith(name + "="):
            return word[len(name) + 1:]
    return None


def main(stdin=None, stderr=None, database=None):
    stdin, stderr = stdin or sys.stdin, stderr or sys.stderr
    raw = stdin.read()
    if not turn_active(database):
        return 0
    try:
        event = json.loads(raw)
    except ValueError:
        print("Blocked: the coordinator guard could not read the hook event.", file=stderr)
        return 2
    reason = check(event) if isinstance(event, dict) else "Blocked: the hook event is not an object."
    if reason:
        print(reason, file=stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
