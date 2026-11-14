#!/usr/bin/env python3
"""Read a site's current login cookies from Google Chrome on this Mac.

Used by the VSiN pull on Jeremy's Mac (self-hosted GitHub runner) so nobody has to paste
cookies into GitHub secrets: whenever Chrome is signed in to the site, the pull uses that
session. Nothing is written to disk or the repo; the cookie string is only returned.

How (macOS Chrome): every profile keeps a SQLite cookie DB (<profile>/Cookies or
<profile>/Network/Cookies). Values are AES-128-CBC encrypted with a key derived from the
"Chrome Safe Storage" password in the login Keychain (PBKDF2-SHA1, salt "saltysalt",
1003 rounds, IV = 16 spaces). Newer Chrome (DB meta version >= 24) prefixes the plaintext
with a 32-byte hash of the host, which is dropped.
The first time, macOS asks whether this may read "Chrome Safe Storage": click Always Allow.

Every profile is checked; the one that used the site's cookies most recently wins, so the
user doesn't need to know which Chrome profile is signed in.
Stdlib only (Python 3.9+), plus the macOS `security` and `openssl` commands.

CLI check:  python3 chrome_cookies.py vsin.com   -> prints profile + cookie names (not values)
"""
import glob, hashlib, os, shutil, sqlite3, subprocess, sys, tempfile, time

CHROME_DIR = os.path.expanduser("~/Library/Application Support/Google/Chrome")
LAST_DIAG = {}  # per-profile summary of the last cookie_header() call: names only, never values
CHROME_EPOCH_OFFSET = 11644473600  # seconds between 1601-01-01 and 1970-01-01


LOGIN_KEYCHAIN = os.path.expanduser("~/Library/Keychains/login.keychain-db")
# Optional fallback for runners that can't open the keychain: a file only readable by this
# Mac user, holding the "Chrome Safe Storage" password (never in the repo or GitHub).
KEY_FILE = os.path.expanduser("~/.config/odds-pipeline/chrome_safe_storage")


def _safe_storage_key():
    errors = []
    for extra in ([], [LOGIN_KEYCHAIN]):        # default search list, then the login keychain by path
        pw = subprocess.run(["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage"] + extra,
                            capture_output=True, text=True, timeout=120)
        if pw.returncode == 0 and pw.stdout.strip():
            return hashlib.pbkdf2_hmac("sha1", pw.stdout.strip().encode(), b"saltysalt", 1003, 16)
        errors.append((pw.stderr or "").strip().splitlines()[-1:] or [f"exit {pw.returncode}"])
    if os.path.isfile(KEY_FILE):
        with open(KEY_FILE) as f:
            secret = f.read().strip()
        if secret:
            return hashlib.pbkdf2_hmac("sha1", secret.encode(), b"saltysalt", 1003, 16)
    detail = " | ".join(e[0] for e in errors)
    raise RuntimeError("couldn't read 'Chrome Safe Storage' from the Keychain: " + detail[:200])


def _decrypt(enc, key, strip_hash):
    if not enc[:3] in (b"v10", b"v11"):
        return enc.decode("utf-8", "replace")          # very old cookies are stored in clear
    r = subprocess.run(["openssl", "enc", "-d", "-aes-128-cbc", "-K", key.hex(), "-iv", "20" * 16],
                       input=enc[3:], capture_output=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError("openssl could not decrypt a cookie: " + r.stderr.decode()[:120])
    out = r.stdout
    # Newer Chrome prefixes a 32-byte binary host hash. Drop it when the DB says so, or when
    # the first 32 bytes clearly aren't text (meta version can lag the actual format).
    if len(out) >= 32 and (strip_hash or not _printable(out[:32])):
        out = out[32:]
    return out.decode("utf-8", "replace")


def _printable(b):
    return all(32 <= c < 127 for c in b)


def _cookie_dbs():
    dbs = []
    for prof in sorted(glob.glob(os.path.join(CHROME_DIR, "*"))):
        for rel in ("Network/Cookies", "Cookies"):
            p = os.path.join(prof, rel)
            if os.path.isfile(p):
                dbs.append((os.path.basename(prof), p))
                break
    return dbs


def _read_rows(db_path, domain):
    """Copy the DB (Chrome keeps it open) and return (meta_version, rows) for the domain."""
    tmp = tempfile.mkdtemp()
    try:
        for suffix in ("", "-journal", "-wal", "-shm"):
            if os.path.exists(db_path + suffix):
                shutil.copy2(db_path + suffix, os.path.join(tmp, "Cookies" + suffix))
        con = sqlite3.connect(os.path.join(tmp, "Cookies"))
        try:
            ver = int(con.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0])
        except Exception:
            ver = 0
        rows = con.execute(
            "SELECT host_key, name, value, encrypted_value, expires_utc, last_access_utc FROM cookies "
            "WHERE host_key = ? OR host_key LIKE ?", (domain, "%." + domain)).fetchall()
        con.close()
        return ver, rows
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def cookie_header(domain):
    """Return (Cookie header string, profile name) for `domain` (e.g. "vsin.com")."""
    if not os.path.isdir(CHROME_DIR):
        raise RuntimeError("Google Chrome data folder not found on this Mac")
    now_chrome = (time.time() + CHROME_EPOCH_OFFSET) * 1_000_000
    best = None
    LAST_DIAG.clear()
    for prof, path in _cookie_dbs():
        try:
            ver, rows = _read_rows(path, domain)
        except Exception as e:
            LAST_DIAG[prof] = f"unreadable: {e}"[:120]
            continue
        rows = [r for r in rows if not r[4] or r[4] > now_chrome]          # drop expired
        LAST_DIAG[prof] = f"{len(rows)} live cookies (db v{ver})"
        if rows:
            last = max(r[5] or 0 for r in rows)
            if best is None or last > best[0]:
                best = (last, prof, ver, rows)
    if not best:
        raise RuntimeError(f"no {domain} cookies in any Chrome profile (sign in to {domain} in Chrome)")
    _, prof, ver, rows = best
    key = _safe_storage_key()
    pairs = {}
    for host, name, value, enc, _exp, _last in sorted(rows, key=lambda r: len(r[0])):  # specific host wins
        pairs[name] = value or _decrypt(enc, key, strip_hash=ver >= 24)
    bad = [k for k, v in pairs.items() if not _printable(v.encode("utf-8", "replace"))]
    LAST_DIAG["chosen"] = prof
    LAST_DIAG["cookies"] = ", ".join(f"{h}:{n}" for h, n, *_ in rows)[:600]   # names only, never values
    if bad:
        LAST_DIAG["garbled"] = ", ".join(bad)[:200]
    return "; ".join(f"{k}={v}" for k, v in pairs.items()), prof


if __name__ == "__main__":
    dom = sys.argv[1] if len(sys.argv) > 1 else "vsin.com"
    header, profile = cookie_header(dom)
    names = [kv.split("=", 1)[0] for kv in header.split("; ")]
    print(f"Chrome profile '{profile}': {len(names)} {dom} cookies: {', '.join(names)}")
