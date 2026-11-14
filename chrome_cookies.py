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
CHROME_EPOCH_OFFSET = 11644473600  # seconds between 1601-01-01 and 1970-01-01


def _safe_storage_key():
    pw = subprocess.run(["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage"],
                        capture_output=True, text=True, timeout=120)
    if pw.returncode != 0 or not pw.stdout.strip():
        raise RuntimeError("couldn't read 'Chrome Safe Storage' from the Keychain "
                           "(on the Mac, allow access when macOS asks: 'Always Allow')")
    return hashlib.pbkdf2_hmac("sha1", pw.stdout.strip().encode(), b"saltysalt", 1003, 16)


def _decrypt(enc, key, strip_hash):
    if not enc[:3] in (b"v10", b"v11"):
        return enc.decode("utf-8", "replace")          # very old cookies are stored in clear
    r = subprocess.run(["openssl", "enc", "-d", "-aes-128-cbc", "-K", key.hex(), "-iv", "20" * 16],
                       input=enc[3:], capture_output=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError("openssl could not decrypt a cookie: " + r.stderr.decode()[:120])
    out = r.stdout[32:] if strip_hash else r.stdout
    return out.decode("utf-8", "replace")


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
    for prof, path in _cookie_dbs():
        try:
            ver, rows = _read_rows(path, domain)
        except Exception:
            continue
        rows = [r for r in rows if not r[4] or r[4] > now_chrome]          # drop expired
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
    return "; ".join(f"{k}={v}" for k, v in pairs.items()), prof


if __name__ == "__main__":
    dom = sys.argv[1] if len(sys.argv) > 1 else "vsin.com"
    header, profile = cookie_header(dom)
    names = [kv.split("=", 1)[0] for kv in header.split("; ")]
    print(f"Chrome profile '{profile}': {len(names)} {dom} cookies: {', '.join(names)}")
