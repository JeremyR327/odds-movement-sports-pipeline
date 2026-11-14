#!/usr/bin/env python3
"""Pull VSiN Pro DK + Circa betting splits and the public Circa line tracker.

Runs in GitHub Actions on Jeremy's Mac (self-hosted runner). With VSIN_COOKIE_SOURCE=chrome
(set by main.yml) it reads the current vsin.com login cookie from Chrome on the Mac
(chrome_cookies.py), so no cookie has to be pasted anywhere; if that fails it falls back to
the VSIN_COOKIE secret.
Writes timestamped CSVs under data/YYYY-MM-DD/ so repeated runs show line and
split movement (and which book moved first).

Exit codes: 0 = everything pulled; 1 = some sources failed (see status.json);
2 = VSiN cookie missing/expired (paywall) -> refresh the secret.
"""
import csv, json, os, re, sys, time, urllib.error, urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

SPORTS = ["NFL", "CFB", "NBA", "CBB"]          # VSiN sport codes (CBB to verify on first run)
SPLITS = "https://data.vsin.com/betting-splits/?source={src}&sport={sport}"
TRACKER = {                                     # public pages; NFL confirmed, others to verify
    "NFL": "https://data.vsin.com/nfl/vegas-odds-linetracker/",
    "CFB": "https://data.vsin.com/college-football/vegas-odds-linetracker/",
    "NBA": "https://data.vsin.com/nba/vegas-odds-linetracker/",
    "CBB": "https://data.vsin.com/college-basketball/vegas-odds-linetracker/",
}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
NOW = datetime.now(ZoneInfo("America/New_York"))
OUTDIR = os.path.join("data", NOW.strftime("%Y-%m-%d"))
STAMP = NOW.strftime("%H%M")


DIAG = {}  # first 403 seen: who answered and how (written to status.json)


def get(url, cookie=None):
    # Browser-like headers: some bot filters 403 a request that only sends a User-Agent.
    h = {"User-Agent": UA,
         "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
         "Accept-Language": "en-US,en;q=0.9",
         "Referer": "https://data.vsin.com/",
         "Upgrade-Insecure-Requests": "1"}
    if cookie:
        h["Cookie"] = cookie
    for attempt in range(3):  # retry dropped/truncated transfers and the odd 403/429
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=40) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and not DIAG:
                body = e.read(600).decode("utf-8", "replace")
                DIAG.update({"url": url, "code": e.code, "server": e.headers.get("server", ""),
                             "cf_ray": e.headers.get("cf-ray", ""), "cf_mitigated": e.headers.get("cf-mitigated", ""),
                             "body_start": re.sub(r"\s+", " ", body)[:300]})
            # A block answers every retry the same way: one retry for 403, then move on
            # (12 blocked URLs x 3 slow retries would blow the 8-minute job limit).
            if attempt == 2 or e.code not in (403, 429, 500, 502, 503, 504) or (e.code == 403 and attempt == 1):
                raise
            time.sleep(5 * (attempt + 1))
        except Exception:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))


def table_rows(html):
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S):
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)]
        cells = [c for c in cells if c != ""]
        if cells:
            out.append(cells)
    return out


def pct(s):
    m = re.search(r"-?\d+(\.\d+)?", s or "")
    return float(m.group(0)) if m else None


def parse_splits(html):
    """Pairs of team rows: team, spread, handle%, bets%, total, handle%, bets%, ML, handle%, bets%."""
    from html import unescape  # local import: the `html` argument shadows the module name

    games, day, pend = [], "", None
    for c in table_rows(html):
        # Cells arrive HTML-escaped: the split-history button is "&#8634;" (↺), "&amp;" in names.
        c = [unescape(x) for x in c]
        if re.match(r"^(CFB|NFL|NBA|CBB|NCAAB|CBK) - ", c[0]):
            # Header reads "NFL - Thursday, Nov 12 Nov 12" (date printed twice); keep one copy.
            day, pend = re.sub(r"(\b\w{3} \d{1,2})\s+\1$", r"\1", c[0]), None
            continue
        q = c[1:] if (c[0] == "↺" or re.fullmatch(r"\d+", c[0])) else c
        if len(q) < 10:
            continue
        t = {"team": re.sub(r"^\(\d+\)\s*", "", q[0]), "spread": q[1], "sp_handle": pct(q[2]), "sp_bets": pct(q[3]),
             "total": q[4], "ov_handle": pct(q[5]), "ov_bets": pct(q[6]),
             "ml": q[7], "ml_handle": pct(q[8]), "ml_bets": pct(q[9])}
        if pend is None:
            pend = t
        else:
            games.append((day, pend, t)); pend = None
    return games


def parse_tracker(html):
    """Circa OPEN + CURRENT full-game lines from the public VSiN line tracker.

    Page layout (one <table class="sp-table">):
      <thead>  book headers; the first <th> holds the first date ("Thu, Nov 12").
               Set A = Circa | Boomers | BetMGM | Caesars, set B = Westgate | Stations |
               South Point | Wynn. Set B is an alternate column set on the SAME rows
               (hidden by CSS / a toggle), not a second list of games.
      <tbody class="sp-tbody-fg">  Full Game lines  <- parsed
      <tbody class="sp-tbody-1h">  1st Half lines (same games, hidden by default) <- ignored
    In a tbody each game is 3 rows: OPEN row (tip time + opening line, quoted from the
    away side), away row, home row. Header rows with class sp-date-book-head start a
    new date. Every book is 3 cells (SPR, ML, TOT); "-" means no line.
    """
    from html import unescape  # local import: the `html` argument shadows the module name

    def text(frag):
        return unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", frag))).strip()

    def val(frag):  # "-" placeholders -> ""; drop line-move arrows (sp-arrow-up/dn ▲▼)
        t = re.sub(r"\s+", " ", re.sub(r"[▲▼]", "", text(frag))).strip()
        return "" if t in ("-", "- -") else t

    fg = re.search(r'<tbody[^>]*class="[^"]*sp-tbody-fg[^"]*"[^>]*>(.*?)</tbody>', html, flags=re.S)
    if not fg:
        return []
    thead = re.search(r"<thead[^>]*>(.*?)</thead>", html, flags=re.S)
    thead = thead.group(1) if thead else ""

    # Locate Circa's 3 columns from the header (cell 0 is the game/team cell).
    books = []
    for cls in ("sp-book-set-a-head", "sp-book-set-b-head"):
        m = re.search(r'<tr[^>]*class="[^"]*sp-header-books[^"]*' + cls + r'[^"]*"[^>]*>(.*?)</tr>', thead, flags=re.S)
        if m:
            books += [text(b) for b in re.findall(r'<th[^>]*sp-book-group[^>]*>(.*?)</th>', m.group(1), flags=re.S)]
    if "Circa" not in books:
        raise ValueError(f"Circa not found in tracker header: {books}")
    base = 1 + 3 * books.index("Circa")

    d = re.search(r'<th[^>]*sp-game-th[^>]*>(.*?)</th>', thead, flags=re.S)
    date = text(d.group(1)) if d else ""

    rows = []  # (class attr, [cell html, ...])
    for attrs, body in re.findall(r"<tr([^>]*)>(.*?)</tr>", fg.group(1), flags=re.S):
        cls = re.search(r'class="([^"]*)"', attrs)
        rows.append((cls.group(1) if cls else "", re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", body, flags=re.S)))

    games, i = [], 0
    while i < len(rows):
        cls, cells = rows[i]
        if "sp-date-book-head" in cls and "sp-header-books" in cls:
            if cells and text(cells[0]):
                date = text(cells[0])
            i += 1
            continue
        if "sp-row-open" not in cls or i + 2 >= len(rows):
            i += 1
            continue
        o, a, h = cells, rows[i + 1][1], rows[i + 2][1]
        i += 3
        if min(len(o), len(a), len(h)) < base + 3:
            continue
        tip = re.search(r"\d+:\d+ [AP]M", text(o[0]))
        games.append({"date": date, "tip": tip.group(0) if tip else "",
                      "away": text(a[0]), "home": text(h[0]),
                      "circa_open_away_spread": val(o[base]), "circa_open_away_ml": val(o[base + 1]),
                      "circa_open_total": val(o[base + 2]),
                      "circa_away_spread": val(a[base]), "circa_away_ml": val(a[base + 1]),
                      "circa_total": val(a[base + 2]),
                      "circa_home_spread": val(h[base]), "circa_home_ml": val(h[base + 1]),
                      "circa_home_total": val(h[base + 2])})
    return games


def write(name, rows):
    if not rows:
        return
    os.makedirs(OUTDIR, exist_ok=True)
    path = os.path.join(OUTDIR, f"{STAMP}_{name}.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def page_markers(html):
    """What the page itself says about the login (no personal data, just yes/no markers)."""
    low = html.lower()
    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    return {"bytes": len(html), "title": re.sub(r"\s+", " ", title.group(1)).strip()[:80] if title else "",
            **{w: (w in low) for w in ("logout", "log out", "sign out", "my account", "log in", "login",
                                       "sign in", "subscribe", "vsin pro", "upgrade")}}


def login_probe(chrome_cookie):
    """Logged-out free view: fetch one splits page with each cookie variant and count games,
    to tell 'Chrome isn't signed in' from 'VSiN wants something we don't send'."""
    url = SPLITS.format(src="DK", sport="CFB")
    pairs = [kv for kv in chrome_cookie.split("; ") if "=" in kv]
    keep = re.compile(r"^(PHPSESSID|wordpress|wp_|__ut|__tac|__tae|__pat|__pid|__pvi|cf_clearance|xbc|__tbc|"
                      r"_pc_|piano|tp_|sess|auth|token|user|member|login)", re.I)
    variants = {"chrome_all": chrome_cookie,
                "chrome_login_only": "; ".join(kv for kv in pairs if keep.match(kv)),
                "secret": os.environ.get("VSIN_COOKIE", "").strip(),
                "no_cookie": ""}
    out = {"chrome_names_all": ", ".join(kv.split("=", 1)[0] for kv in pairs)[:1500],
           "chrome_header_bytes": len(chrome_cookie)}
    for name, c in variants.items():
        if name != "no_cookie" and not c:
            out[name] = "empty"
            continue
        try:
            html = get(url, c or None)
            out[name] = {"games": len(parse_splits(html)), **page_markers(html)}
        except Exception as e:
            out[name] = f"error: {e}"[:150]
    return out


def main():
    status, paywalled = {"pulled_et": NOW.isoformat(timespec="minutes")}, False
    cookie = ""
    if os.environ.get("VSIN_COOKIE_SOURCE", "").lower() == "chrome":
        try:
            from chrome_cookies import cookie_header
            cookie, profile = cookie_header("vsin.com")
            status["cookie_source"] = f"Chrome on the Mac (profile '{profile}')"
            import chrome_cookies
            status["chrome_diag"] = dict(chrome_cookies.LAST_DIAG)
        except Exception as e:
            status["cookie_source"] = f"Chrome failed ({e}); using the VSIN_COOKIE secret"
    if not cookie:
        cookie = os.environ.get("VSIN_COOKIE", "").strip()
        status.setdefault("cookie_source", "VSIN_COOKIE secret" if cookie else "none")
    for sport in SPORTS:
        for src in ("DK", "CIRCA"):
            key = f"splits_{src}_{sport}"
            try:
                g = parse_splits(get(SPLITS.format(src=src, sport=sport), cookie or None))
                rows = [{"pulled_et": status["pulled_et"], "day": d, "away": a["team"], "home": h["team"],
                         **{f"away_{k}": v for k, v in a.items() if k != "team"},
                         **{f"home_{k}": v for k, v in h.items() if k != "team"}} for d, a, h in g]
                write(key, rows)
                status[key] = f"ok {len(rows)} games" if rows else "0 games (paywall or empty)"
            except Exception as e:
                status[key] = f"error: {e}"
        try:
            t = parse_tracker(get(TRACKER[sport]))
            write(f"circa_{sport}", [{"pulled_et": status["pulled_et"], **r} for r in t])
            status[f"circa_{sport}"] = f"ok {len(t)} games"
        except Exception as e:
            status[f"circa_{sport}"] = f"error: {e}"
    # Paywall check: if no sport returned DK splits, the cookie is missing or expired.
    if not any(v.startswith("ok") for k, v in status.items() if k.startswith("splits_DK")):
        paywalled = True
        tracker_blocked = all("403" in str(v) for k, v in status.items() if k.startswith("circa_"))
        status["alert"] = ("VSiN is blocking GitHub's servers (403 on the public line tracker too, which uses no cookie); "
                           "refreshing VSIN_COOKIE will not fix this" if tracker_blocked else
                           "VSiN cookie missing or expired: refresh the VSIN_COOKIE secret")
    # Logged-out check: the free view shows ~1 game per splits page while the public line
    # tracker still lists many. That means the cookie no longer logs in (Nov 13, 10:19 PM pull).
    def n_games(v):
        m = re.match(r"ok (\d+) games", str(v))
        return int(m.group(1)) if m else 0
    dk_max = max([n_games(v) for k, v in status.items() if k.startswith("splits_DK")] or [0])
    tracker_max = max([n_games(v) for k, v in status.items() if k.startswith("circa_")] or [0])
    if not paywalled and dk_max <= 2 and tracker_max >= 8:
        paywalled = True
        status["alert"] = ("VSiN splits show the logged-out free view (<=2 games per page) while the line "
                           "tracker lists many: the VSiN login isn't working. On the Mac, open data.vsin.com "
                           "in Chrome and sign in (or refresh the VSIN_COOKIE secret)")
    if paywalled and dk_max <= 2:
        status["login_probe"] = login_probe(cookie)
    if DIAG:
        status["diag_403"] = DIAG
    os.makedirs("data", exist_ok=True)
    with open(os.path.join("data", "status.json"), "w") as f:
        json.dump(status, f, indent=2)
    print(json.dumps(status, indent=2))
    sys.exit(2 if paywalled else (1 if any("error" in str(v) for v in status.values()) else 0))


if __name__ == "__main__":
    main()
