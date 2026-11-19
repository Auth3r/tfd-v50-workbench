"""Summarise a launcher run: event chain for the login/bridge path."""
import json, sys, pathlib

DIR = pathlib.Path(sys.argv[1])
EV = DIR / "events.jsonl"
WANT = {
    "bridge_ready", "bridge_error", "bridge_skip_attach", "bridge_resumed",
    "native_title_login_rearmed", "native_title_login_opened",
    "launcher_login_ticket_bound", "native_launcher_account_login",
    "connected", "client_exit_observed", "native_account_loaded",
    "native_title_creation_platform_released", "native_title_creation_bridge_ready",
}
rows = [json.loads(l) for l in EV.read_text(encoding="utf-8").splitlines() if l.strip()]
print("run", DIR.name, "events", len(rows), "last", rows[-1].get("elapsed"), rows[-1].get("event"))
kinds = sorted({r.get("event") for r in rows})
print("distinct events:", len(kinds))
for r in rows:
    n = r.get("event")
    if n in WANT:
        extra = {k: v for k, v in r.items() if k not in ("elapsed", "event")}
        print("  %8s %-40s %s" % (r.get("elapsed"), n, str(extra)[:160]))
