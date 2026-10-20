#!/usr/bin/env python3
"""Back the vault up off this machine: one encrypted archive a night, written to a folder that syncs somewhere else.

The vault's own git history (if it has one) protects against a bad edit; it does not survive a dead disk or a lost
laptop. A copy elsewhere does. KRouter does not talk to any cloud: it writes an encrypted archive into a folder you
choose (iCloud Drive, Dropbox, OneDrive, a Baidu or Google Drive sync folder, a USB disk, a NAS), and that folder's
own client carries it away. Each archive is written once and never edited, so a sync client cannot half-merge it.

- **What is in it:** the whole vault folder, its `.git` included (so the history comes too), minus editor state and
  caches (`.trash`, `.obsidian/workspace*.json`, `.obsidian/cache`, `__pycache__`, `.DS_Store`).
- **Encrypted, always.** Vaults hold plugin settings with tokens and pasted text; an archive leaves the machine only as
  AES-256 (`openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -md sha256`), with an HMAC-SHA256 over the ciphertext
  (stdlib, its own PBKDF2 salt) so a damaged or altered file is caught before it is opened. No unencrypted mode.
- **The passphrase** is `KROUTER_BACKUP_PASSPHRASE` in the keys file (`~/.dsh-krouter-keys.env`, outside the vault, so
  it is never inside the archive). `init` makes a strong one. Without it no archive can be opened: keep a copy in a
  password manager, then run `saved` so `status` stops reminding you.
- **Checked every time.** After writing, the archive is opened again in a temporary folder: HMAC, decryption, the page
  count, and `git fsck` on the history. Only a backup that restored counts as the last good one.
- **Kept:** the newest 7, plus the newest of each of the last 4 weeks and 6 months.
- **Two places are better than one.** `KROUTER_BACKUP_DIR` may name several folders, separated by `|` (a cloud folder
  and a USB disk, say); each gets its own archive, checked on its own, and one failing does not stop the others.

    backup.py init --dir "~/Library/Mobile Documents/com~apple~CloudDocs/KRouter backups"
    backup.py saved                       # after you copied the passphrase somewhere safe
    backup.py --vault ~/Vault             # one backup now (the nightly job does this when a folder is set)
    backup.py verify --latest             # open the newest archive again, change nothing
    backup.py restore <archive> --into ~/Vault-restored
    backup.py status

Needs `openssl` (macOS and Linux have it; on Windows it comes with Git for Windows). Prints JSON lines; never prints
the passphrase.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import llm  # noqa: E402

PASS_NAME = "KROUTER_BACKUP_PASSPHRASE"
DIR_NAME = "KROUTER_BACKUP_DIR"
ITER = 600_000
SUFFIX = ".tar.gz.enc"
SKIP_DIRS = {".trash", "__pycache__"}
SKIP_FILES = {".DS_Store"}
KEEP_NEWEST, KEEP_WEEKS, KEEP_MONTHS = 7, 4, 6
STALE_DAYS = 3


def state_file() -> Path:
    return Path(os.environ.get("KROUTER_STATE_DIR") or Path.home() / ".local/state/krouter") / "backup.json"


def load_state() -> dict:
    try:
        return json.loads(state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(data: dict) -> None:
    path = state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def setting(name: str) -> str:
    """Environment first, then the keys file. Never printed."""
    val = os.environ.get(name, "").strip()
    if val:
        return val
    path = llm.keys_file()
    if path.is_file():
        return llm._parse(path.read_text(encoding="utf-8", errors="replace")).get(name, "")
    return ""


def openssl() -> str:
    found = shutil.which("openssl")
    if found:
        return found
    for cand in (r"C:\Program Files\Git\usr\bin\openssl.exe", r"C:\Program Files\Git\mingw64\bin\openssl.exe"):
        if Path(cand).is_file():
            return cand
    raise SystemExit(json.dumps({"backup": "failed", "reason": "openssl not found (macOS and Linux have it; on "
                                 "Windows install Git for Windows)"}))


def _crypt(src: Path, dst: Path, passphrase: str, decrypt: bool) -> None:
    argv = [openssl(), "enc", "-aes-256-cbc", "-pbkdf2", "-iter", str(ITER), "-md", "sha256", "-salt",
            "-in", str(src), "-out", str(dst), "-pass", "env:KROUTER_BACKUP_PASS_FOR_OPENSSL"]
    if decrypt:
        argv.insert(2, "-d")
    env = {**os.environ, "KROUTER_BACKUP_PASS_FOR_OPENSSL": passphrase}  # 只给这个子进程，不进命令行参数
    res = subprocess.run(argv, env=env, capture_output=True, text=True)
    if res.returncode != 0:
        raise ValueError("decryption failed (wrong passphrase or damaged file)" if decrypt else
                         "encryption failed: " + res.stderr.strip()[-200:])


def _mac(path: Path, passphrase: str, salt: bytes) -> str:
    key = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, ITER)
    h = hmac.new(key, digestmod=hashlib.sha256)
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _skip(rel: Path) -> bool:
    parts = rel.parts
    if any(p in SKIP_DIRS for p in parts) or rel.name in SKIP_FILES:
        return True
    if parts[:1] == (".obsidian",) and (rel.name.startswith("workspace") or "cache" in parts[1:2]):
        return True
    return False


def pack(vault: Path, out: Path) -> dict:
    pages = files = 0
    with tarfile.open(out, "w:gz") as tar:
        for path in sorted(vault.rglob("*")):
            rel = path.relative_to(vault)
            if _skip(rel) or path.is_symlink() or not path.is_file():
                continue
            tar.add(path, arcname=str(Path(vault.name) / rel), recursive=False)
            files += 1
            pages += path.suffix == ".md" and ".git" not in rel.parts
    return {"files": files, "pages": pages}


def git_head(vault: Path) -> str:
    if not (vault / ".git").is_dir():
        return ""
    res = subprocess.run(["git", "-C", str(vault), "rev-parse", "HEAD"], capture_output=True, text=True)
    return res.stdout.strip() if res.returncode == 0 else ""


def manifest_of(archive: Path) -> Path:
    return archive.with_name(archive.name[: -len(SUFFIX)] + ".json")


def make(vault: Path, dest: Path, passphrase: str) -> dict:
    dest.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = dest / f"krouter-backup-{vault.name}-{stamp}{SUFFIX}"
    with tempfile.TemporaryDirectory(prefix="krouter-backup-") as tmp:
        plain = Path(tmp) / "vault.tar.gz"
        counts = pack(vault, plain)
        part = archive.with_name(archive.name + ".part")
        _crypt(plain, part, passphrase, decrypt=False)
        salt = secrets.token_bytes(16)
        meta = {"created": datetime.now().isoformat(timespec="seconds"), "vault": vault.name, **counts,
                "git_head": git_head(vault), "bytes": part.stat().st_size, "cipher": "openssl aes-256-cbc pbkdf2 "
                f"sha256 iter {ITER}", "hmac_sha256": _mac(part, passphrase, salt), "hmac_salt": salt.hex()}
        os.replace(part, archive)  # 写完整了才改名：同步客户端看不到半个文件
    manifest_of(archive).write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"archive": str(archive), **meta}


def open_archive(archive: Path, passphrase: str, into: Path) -> dict:
    """HMAC, decrypt, extract into `into` (which must not exist), check the page count and the history."""
    mpath = manifest_of(archive)
    meta = json.loads(mpath.read_text(encoding="utf-8")) if mpath.is_file() else {}
    if meta.get("hmac_sha256"):
        if not hmac.compare_digest(_mac(archive, passphrase, bytes.fromhex(meta["hmac_salt"])), meta["hmac_sha256"]):
            raise ValueError("HMAC mismatch: wrong passphrase, or the file was damaged or altered")
    if into.exists():
        raise ValueError(f"{into} already exists; restore never writes over a folder")
    with tempfile.TemporaryDirectory(prefix="krouter-restore-") as tmp:
        plain = Path(tmp) / "vault.tar.gz"
        _crypt(archive, plain, passphrase, decrypt=True)
        into.mkdir(parents=True)
        with tarfile.open(plain, "r:gz") as tar:
            members = tar.getmembers()
            for m in members:  # 只解普通文件，路径必须落在目标目录里
                target = (into / m.name).resolve()
                if not m.isfile() or not str(target).startswith(str(into.resolve()) + os.sep):
                    raise ValueError(f"unsafe entry in archive: {m.name}")
            safe = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
            tar.extractall(into, members=members, **safe)
    roots = [p for p in into.iterdir() if p.is_dir()]
    root = roots[0] if len(roots) == 1 else into
    pages = sum(1 for p in root.rglob("*.md") if ".git" not in p.relative_to(root).parts)
    git_ok = None
    if (root / ".git").is_dir():
        res = subprocess.run(["git", "-C", str(root), "fsck", "--no-dangling", "--no-progress"], capture_output=True,
                             text=True)
        git_ok = res.returncode == 0
    if meta.get("pages") is not None and pages != meta["pages"]:
        raise ValueError(f"page count {pages} differs from the manifest's {meta['pages']}")
    if git_ok is False:
        raise ValueError("git fsck failed on the restored history")
    return {"restored": str(root), "pages": pages, "git_ok": git_ok, "created": meta.get("created")}


def archives(dest: Path) -> list[Path]:
    return sorted(dest.glob(f"krouter-backup-*{SUFFIX}"))


def _stamp(path: Path) -> datetime:
    raw = path.name[: -len(SUFFIX)].rsplit("-", 2)[-2:]
    return datetime.strptime("-".join(raw), "%Y%m%d-%H%M%S")


def prune(dest: Path, now: datetime | None = None) -> list[str]:
    """Keep the newest 7, and the newest of each of the last 4 weeks and 6 months; delete the rest (and their
    manifests). Only files this script named are ever touched."""
    now = now or datetime.now()
    found = sorted(archives(dest), key=_stamp, reverse=True)
    keep = set(found[:KEEP_NEWEST])
    weeks, months = {}, {}
    for p in found:
        t = _stamp(p)
        if t >= now - timedelta(weeks=KEEP_WEEKS):
            weeks.setdefault(t.isocalendar()[:2], p)
        if (now.year - t.year) * 12 + now.month - t.month < KEEP_MONTHS:
            months.setdefault((t.year, t.month), p)
    keep |= set(weeks.values()) | set(months.values())
    gone = []
    for p in found:
        if p not in keep:
            p.unlink(missing_ok=True)
            manifest_of(p).unlink(missing_ok=True)
            gone.append(p.name)
    return gone


def dests(raw: str) -> list[Path]:
    return [Path(x.strip()).expanduser() for x in raw.split("|") if x.strip()]


def status() -> dict:
    st = load_state()
    dest = setting(DIR_NAME)
    out = {"backup": "off" if not dest else "on", "dir": dest or None, "last_good": st.get("last_good"),
           "last_error": st.get("last_error"), "passphrase_saved_elsewhere": bool(st.get("passphrase_saved"))}
    if dest:
        out["archives"] = sum(len(archives(d)) for d in dests(dest))
        actions = []
        if not setting(PASS_NAME):
            actions.append(f"no {PASS_NAME} in the keys file: run backup.py init")
        if not st.get("passphrase_saved"):
            actions.append("the backup passphrase is only on this machine: copy it into a password manager, then "
                           "run backup.py saved")
        last = st.get("last_good")
        if not last or datetime.fromisoformat(last) < datetime.now() - timedelta(days=STALE_DAYS):
            actions.append(f"no backup restored cleanly in {STALE_DAYS}+ days" + (f": {st.get('last_error')}"
                                                                                  if st.get("last_error") else ""))
        if actions:
            out["host_action"] = "; ".join(actions)
    return out


def set_key(name: str, value: str) -> None:
    """Add or replace one line in the keys file; the file stays readable by the owner only."""
    path = llm.keys_file()
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    lines = [ln for ln in lines if not ln.strip().startswith((name + "=", "export " + name + "="))]
    lines.append(f"{name}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Encrypted, checked backups of the vault into a folder that syncs "
                                             "elsewhere")
    ap.add_argument("cmd", nargs="?", default="run", choices=["run", "init", "saved", "verify", "restore", "status"])
    ap.add_argument("archive", nargs="?", default="")
    ap.add_argument("--vault", default="")
    ap.add_argument("--to", default="", help="backup folder (default: KROUTER_BACKUP_DIR)")
    ap.add_argument("--dir", default="", help="init: the folder to keep backups in")
    ap.add_argument("--into", default="", help="restore: a new folder to restore into")
    ap.add_argument("--latest", action="store_true", help="verify: the newest archive in the backup folder")
    args = ap.parse_args()

    if args.cmd == "status":
        print(json.dumps(status(), ensure_ascii=False))
        return 0
    if args.cmd == "saved":
        save_state({**load_state(), "passphrase_saved": datetime.now().isoformat(timespec="seconds")})
        print(json.dumps({"passphrase_saved_elsewhere": True}))
        return 0
    if args.cmd == "init":
        made = False
        if not setting(PASS_NAME):
            set_key(PASS_NAME, secrets.token_urlsafe(32))
            made = True
        if args.dir:
            set_key(DIR_NAME, str(Path(args.dir).expanduser()))
        print(json.dumps({"passphrase": "created" if made else "kept", "stored_in": str(llm.keys_file()),
                          "dir": setting(DIR_NAME) or None,
                          "next": f"copy {PASS_NAME} from that file into a password manager (without it no backup "
                                  "can be opened), then run backup.py saved"}, ensure_ascii=False))
        return 0

    passphrase = setting(PASS_NAME)
    dest_raw = args.to or setting(DIR_NAME)
    if args.cmd == "run" and not dest_raw:
        print(json.dumps({"backup": "off", "reason": f"no backup folder (backup.py init --dir <folder>, or "
                                                     f"{DIR_NAME} in the keys file)"}))
        return 0
    if not passphrase:
        print(json.dumps({"backup": "failed", "reason": f"no {PASS_NAME} (backup.py init makes one)"}))
        return 1
    targets = dests(dest_raw) if dest_raw else []
    dest = targets[0] if targets else None

    if args.cmd in ("verify", "restore"):
        archive = Path(args.archive).expanduser() if args.archive else None
        if args.latest or not archive:
            found = archives(dest) if dest else []
            if not found:
                print(json.dumps({"verify": "failed", "reason": "no archive found"}))
                return 1
            archive = max(found, key=_stamp)
        try:
            if args.cmd == "restore":
                if not args.into:
                    ap.error("restore needs --into <new folder>")
                res = open_archive(archive, passphrase, Path(args.into).expanduser())
            else:
                with tempfile.TemporaryDirectory(prefix="krouter-verify-") as tmp:
                    res = open_archive(archive, passphrase, Path(tmp) / "v")
                    res.pop("restored")
        except ValueError as exc:
            print(json.dumps({args.cmd: "failed", "archive": str(archive), "reason": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps({args.cmd: "ok", "archive": str(archive), **res}, ensure_ascii=False))
        return 0

    vault = Path(args.vault or os.environ.get("OBSIDIAN_VAULT") or "").expanduser()
    if not vault.is_dir():
        print(json.dumps({"backup": "failed", "reason": "no vault (--vault or OBSIDIAN_VAULT)"}))
        return 1
    st = load_state()
    results, errors = [], []
    for target in targets:  # 每个位置各写各查，一个失败不拦另一个
        try:
            made = make(vault.resolve(), target, passphrase)
            with tempfile.TemporaryDirectory(prefix="krouter-verify-") as tmp:
                check = open_archive(Path(made["archive"]), passphrase, Path(tmp) / "v")
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            errors.append(f"{target}: {exc}"[:300])
            continue
        results.append({"archive": made["archive"], "pages": made["pages"], "files": made["files"],
                        "bytes": made["bytes"], "git": bool(made["git_head"]), "restore_checked": True,
                        "git_ok": check["git_ok"], "pruned": len(prune(target))})
    now = datetime.now().isoformat(timespec="seconds")
    if results:
        st = {**st, "last_good": now, "last_archive": results[0]["archive"]}
    st["last_error"] = f"{now} " + "; ".join(errors) if errors else None
    save_state(st)
    state = "ok" if not errors else ("partial" if results else "failed")
    print(json.dumps({"backup": state, "places": results, **({"errors": errors} if errors else {}),
                      **(results[0] if len(results) == 1 and not errors else {})}, ensure_ascii=False))
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
