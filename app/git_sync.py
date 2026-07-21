"""Git plumbing: pull before render, commit+push after every save. Push
failures are caught and surfaced as a warning rather than crashing the app
-- GitHub write access may not always be configured yet.
"""
import subprocess
from os.path import dirname, abspath

REPO_ROOT = dirname(dirname(abspath(__file__)))


def _run(args):
    return subprocess.run(
        ["git"] + args, cwd=REPO_ROOT, capture_output=True, text=True, timeout=30
    )


def pull():
    try:
        result = _run(["pull", "--ff-only"])
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)


def commit_and_push(message):
    try:
        _run(["add", "-A"])
        status = _run(["status", "--porcelain"])
        if not status.stdout.strip():
            return True, "nothing to commit"

        commit = _run(["commit", "-m", message])
        if commit.returncode != 0:
            return False, commit.stdout + commit.stderr

        push = _run(["push"])
        if push.returncode != 0:
            return False, "committed locally, but push failed: " + push.stdout + push.stderr
        return True, "committed and pushed"
    except Exception as e:
        return False, str(e)
