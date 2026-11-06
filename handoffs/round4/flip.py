# Applies a workflow's lane statuses to the ledger. Done only if unrefuted and override-free; open DependsOn noted.
import json, os, re, shutil, sys
LED = "D:/Project/FrontRow/frontrow_aws/docs/10 EngineeringLedger"
out, run, *_ = sys.argv[1:]
over = json.loads(os.environ.get("OVERRIDE", "{}"))  # id -> note forcing Blocked
d = json.load(open(out, encoding="utf-8")); d = d.get("result", d) if isinstance(d, dict) else d
d = json.loads(d) if isinstance(d, str) else d
rows = [l.split("\t") for l in open(f"{LED}/engineering_ledger.tsv", encoding="utf-8", newline="").read().split("\n") if l]
h = rows[0]; c = {k: h.index(k) for k in ("ID", "Status", "StatusNote", "DependsOn")}
by = {r[c["ID"]]: r for r in rows[1:]}
rep = {}
for lane in d:
    refuted = {x.split(":")[0].strip() for x in (lane.get("v") or {}).get("rows_refuted", [])}
    for r in lane["rep"]["rows"]:
        st = r["status"]
        if st == "Done" and r["id"] in refuted: st, r["note"] = "Blocked", "Refuted by the verifier. " + r["note"]
        if r["id"] in over: st, r["note"] = "Blocked", over[r["id"]] + " " + r["note"]
        rep[r["id"]] = (lane["key"], (lane.get("v") or {}).get("verdict"), st, r)
status = lambda x: rep[x][2] if x in rep else by[x][c["Status"]]
for _ in range(5):  # settle dependency chains
    for i, (k, v, st, r) in list(rep.items()):
        if st != "Done": continue
        bad = [x for x in re.split(r"[\s,;]+", by[i][c["DependsOn"]]) if x in by and status(x) != "Done"]
        # [JUDGMENT CALL] DoD judges a row on its own AC; an unfinished DependsOn is recorded, not a demotion.
        if bad and "DependsOn not yet Done" not in r["note"]: r["note"] = f"DependsOn not yet Done: {', '.join(bad)}. " + r["note"]
for i, (k, v, st, r) in rep.items():
    if st == "Backlog" or i not in by: continue
    by[i][c["Status"]] = st
    by[i][c["StatusNote"]] = "" if st == "Done" else " ".join(r["note"].split())[:900]
    ev = f"{LED}/evidence/{i}"
    if st == "Done":
        os.makedirs(ev, exist_ok=True)
        open(f"{ev}/README.md", "w", encoding="utf-8").write(
            f"# {i} — Done\n\nLane `{k}`, workflow {run}, 2026-11-06. Verifier verdict: {v}; this row was not refuted.\n\n"
            f"**Evidence:** {r['evidence']}\n\n**Note:** {r['note']}\n")
    elif os.path.isdir(ev) and run in open(f"{ev}/README.md", encoding="utf-8").read():
        shutil.rmtree(ev)  # written by an earlier pass of this same run
open(f"{LED}/engineering_ledger.tsv", "w", encoding="utf-8", newline="").write("".join("\t".join(r) + "\n" for r in rows))
print({s: sum(1 for x in rep.values() if x[2] == s) for s in ("Done", "Blocked", "Backlog")})
print("Done:", sorted(i for i, x in rep.items() if x[2] == "Done"))
