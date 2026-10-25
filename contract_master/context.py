"""Pinned context is extracted from Git objects, never the mutable working tree."""
import json
import os
import subprocess
from pathlib import Path
from .contracts import ContractError, digest, safe_path


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE)


def build(repo, commit, required, destination, reviewed_commits):
    if commit not in reviewed_commits:
        raise ContractError("Master commit is not in the reviewed allowlist")
    resolved = git(repo, "rev-parse", "--verify", commit + "^{commit}").decode().strip()
    if resolved != commit or not required:
        raise ContractError("Use a full reviewed commit and required document list")
    files = {}
    for name in sorted(set(required)):
        safe_path(name)
        entry = git(repo, "ls-tree", commit, "--", name).decode().split()
        if not entry:
            raise ContractError("Missing required context: " + name)
        mode = entry[0]
        if mode != "100644" and mode != "100755":
            raise ContractError("Context must contain regular Git blobs")
        data = git(repo, "show", commit + ":" + name).decode("utf-8")
        files[name] = data
    manifest = {"version": "1.0", "source_commit": commit, "files": files}
    fingerprint = digest(manifest)
    dest = Path(destination) / fingerprint
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / "bundle.json"
    if target.exists():
        if json.loads(target.read_text()) != manifest:
            raise ContractError("Existing bundle differs")
    else:
        temporary = dest / ("bundle." + str(os.getpid()) + ".tmp")
        temporary.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
        temporary.chmod(0o444)
        os.replace(temporary, target)
    return {"source_commit": commit, "digest": fingerprint, "path": str(target.resolve())}


def load(reference, required):
    try:
        manifest = json.loads(Path(reference["path"]).read_text())
        if digest(manifest) != reference["digest"] or manifest["source_commit"] != reference["source_commit"]:
            raise ContractError("Context digest or source mismatch")
        if not set(required).issubset(manifest["files"]):
            raise ContractError("Missing required context")
        for path, text in manifest["files"].items():
            safe_path(path)
            if not isinstance(text, str) or not text.strip():
                raise ContractError("Invalid context content")
        return manifest
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ContractError("Missing or corrupted required context") from exc
