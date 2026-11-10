import json, glob
for f in sorted(glob.glob("cg/*.json")):
    d = json.load(open(f))
    ev = d.get("events", {})
    used = sum(1 for a in d.get("animations", {}).values() if "events" in a)
    print(f, len(ev), "event defs,", used, "animations with events", [(k, v.get("audio")) for k, v in list(ev.items())[:2]])
