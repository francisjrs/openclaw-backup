#!/usr/bin/env python3
import os
import re
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

WORKSPACE = Path('/home/node/.openclaw/workspace')
SCRUBBED = WORKSPACE / 'state' / 'backup_scrubbed'
MANIFEST = WORKSPACE / 'state' / 'backup_last_manifest.json'
# Configure backup repo path via env var BACKUP_REPO_DIR or a local config file.
BACKUP_REPO_FILE = WORKSPACE / '.secrets' / 'backup_repo_dir'
backup_repo_dir = os.environ.get('BACKUP_REPO_DIR', '').strip()
if not backup_repo_dir and BACKUP_REPO_FILE.exists():
    backup_repo_dir = BACKUP_REPO_FILE.read_text().strip()
BACKUP_REPO = Path(backup_repo_dir) if backup_repo_dir else None

EXCLUDE_DIRS = {'.git', 'node_modules', 'state/backup_scrubbed'}
EXCLUDE_FILES = {
    '.secrets/icloud_app_password',
}

REPLACERS = [
    (re.compile(r'(?i)(api[_-]?key\s*[:=]\s*)([^\s"\']+)'), r'\1[API_KEY]'),
    (re.compile(r'(?i)(token\s*[:=]\s*)([^\s"\']+)'), r'\1[TOKEN]'),
    (re.compile(r'(?i)(password\s*[:=]\s*)([^\s"\']+)'), r'\1[PASSWORD]'),
    (re.compile(r'[ICLOUD_APP_PASSWORD]'), '[ICLOUD_APP_PASSWORD]'),
    (re.compile(r'(?i)franciscojrs@me\.com'), '[ICLOUD_EMAIL]'),
]


def is_text_file(path: Path) -> bool:
    try:
        data = path.read_bytes()[:4096]
        if b'\x00' in data:
            return False
        data.decode('utf-8')
        return True
    except Exception:
        return False


def scrub_text(text: str):
    changed = False
    out = text
    for rx, repl in REPLACERS:
        new = rx.sub(repl, out)
        if new != out:
            changed = True
            out = new
    return out, changed


def rel_excluded(rel: str) -> bool:
    rel = rel.strip('/')
    if rel in EXCLUDE_FILES:
        return True
    for ex in EXCLUDE_DIRS:
        if rel == ex or rel.startswith(ex + '/'):
            return True
    return False


def build_scrubbed_tree():
    if SCRUBBED.exists():
        shutil.rmtree(SCRUBBED)
    SCRUBBED.mkdir(parents=True, exist_ok=True)

    findings = []
    for p in WORKSPACE.rglob('*'):
        if p.is_dir():
            continue
        rel = str(p.relative_to(WORKSPACE))
        if rel_excluded(rel):
            continue
        out = SCRUBBED / rel
        out.parent.mkdir(parents=True, exist_ok=True)

        if is_text_file(p):
            txt = p.read_text(errors='replace')
            scrubbed, changed = scrub_text(txt)
            out.write_text(scrubbed)
            if changed:
                findings.append(rel)
        else:
            shutil.copy2(p, out)
    return findings


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)


def summarize_changes():
    if not MANIFEST.exists():
        return 'initial backup snapshot'
    try:
        prev = json.loads(MANIFEST.read_text())
    except Exception:
        prev = {}
    now = {
        str(p.relative_to(SCRUBBED)): p.stat().st_mtime
        for p in SCRUBBED.rglob('*') if p.is_file()
    }
    added = [k for k in now if k not in prev]
    removed = [k for k in prev if k not in now]
    touched = [k for k in now if k in prev and now[k] != prev[k]]
    return f"added={len(added)}, updated={len(touched)}, removed={len(removed)}"


def update_manifest():
    m = {
        str(p.relative_to(SCRUBBED)): p.stat().st_mtime
        for p in SCRUBBED.rglob('*') if p.is_file()
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m, indent=2))


def sync_to_repo():
    if BACKUP_REPO is None:
        raise RuntimeError("backup repo missing: set BACKUP_REPO_DIR or /home/node/.openclaw/workspace/.secrets/backup_repo_dir")
    if not BACKUP_REPO.exists():
        raise RuntimeError(f"backup repo missing: {BACKUP_REPO}")
    git_dir = BACKUP_REPO / '.git'
    if not git_dir.exists():
        raise RuntimeError(f"not a git repo: {BACKUP_REPO}")

    # sync files
    for p in SCRUBBED.rglob('*'):
        if p.is_dir():
            continue
        rel = p.relative_to(SCRUBBED)
        dst = BACKUP_REPO / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)

    # Remove repo files that no longer exist in scrubbed tree (except .git)
    for p in BACKUP_REPO.rglob('*'):
        if '.git' in p.parts:
            continue
        if p.is_dir():
            continue
        rel = p.relative_to(BACKUP_REPO)
        if not (SCRUBBED / rel).exists():
            p.unlink()


def git_commit_and_push(summary):
    add = run(['git', 'add', '-A'], BACKUP_REPO)
    if add.returncode != 0:
        raise RuntimeError(f"git add failed: {add.stderr.strip()}")

    status = run(['git', 'status', '--porcelain'], BACKUP_REPO)
    if status.returncode != 0:
        raise RuntimeError(f"git status failed: {status.stderr.strip()}")
    if not status.stdout.strip():
        print('No backup changes to commit.')
        return

    msg = f"backup {datetime.now().strftime('%Y-%m-%d')}: {summary}"
    commit = run(['git', 'commit', '-m', msg], BACKUP_REPO)
    if commit.returncode != 0:
        raise RuntimeError(f"git commit failed: {commit.stderr.strip()}")

    push = run(['git', 'push'], BACKUP_REPO)
    if push.returncode != 0:
        raise RuntimeError(f"git push failed: {push.stderr.strip()}")


def main():
    findings = build_scrubbed_tree()
    summary = summarize_changes() + f", scrubbed_files={len(findings)}"
    sync_to_repo()
    git_commit_and_push(summary)
    update_manifest()
    print(f"Backup OK: {summary}")
    if findings:
        print('Redacted secrets in:')
        for f in findings[:30]:
            print(f"- {f}")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}")
        raise
