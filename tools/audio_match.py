# Second pass: finds which AudioClip each spine sound path should use.
# Run from the folder that contains "assets":  python audio_match.py [viewer/cg dir]
import platform, sys, os, json, glob, collections
from unittest.mock import MagicMock
platform.system = lambda: "Linux"
sys.platform = "linux"
for m in ("fmod_toolkit", "fmod_toolkit.libfmod", "pyfmodex"):
    sys.modules[m] = MagicMock()
import UnityPy

cg_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/pubpets_archive/viewer/cg")

clips = []
for root, _, files in os.walk("assets"):
    for f in files:
        if f.endswith((".dat", ".json", ".resource")) or f == "boot.config":
            continue
        try:
            env = UnityPy.load(os.path.join(root, f))
        except Exception:
            continue
        for o in env.objects:
            if o.type.name != "AudioClip":
                continue
            try:
                d = o.read()
                r = getattr(d, "m_Resource", None)
                af = getattr(o, "assets_file", None)
                clips.append(dict(
                    inner=getattr(af, "name", "?"), pid=o.path_id, name=getattr(d, "m_Name", ""),
                    length=round(getattr(d, "m_Length", 0) or 0, 2),
                    src=getattr(r, "m_Source", "") if r else "",
                    off=getattr(r, "m_Offset", 0) if r else 0,
                    size=getattr(r, "m_Size", 0) if r else 0))
            except Exception as e:
                print("skip", e)

for c in clips:
    c["key"] = (c["src"], c["off"], c["size"]) if c["src"] else (c["inner"], c["pid"])

with open("audio_clips.tsv", "w", encoding="utf-8") as fh:
    cols = ["inner", "pid", "name", "length", "src", "off", "size"]
    fh.write("\t".join(cols) + "\n")
    for c in clips:
        fh.write("\t".join(str(c[k]) for k in cols) + "\n")
print(len(clips), "clips,", len({c["key"] for c in clips}), "distinct audio blobs")
print("clips per file:", collections.Counter(c["inner"] for c in clips).most_common(12))

used_by = collections.defaultdict(set)
for f in glob.glob(os.path.join(cg_dir, "*.json")):
    try:
        ev = json.load(open(f, encoding="utf-8")).get("events", {})
    except Exception:
        continue
    for v in ev.values():
        if v.get("audio"):
            used_by[v["audio"]].add(os.path.basename(f)[:-5])

by_name = collections.defaultdict(list)
for c in clips:
    by_name[c["name"].lower()].append(c)

none, one, many = [], [], []
for p in sorted(used_by):
    cand = by_name.get(os.path.splitext(os.path.basename(p))[0].lower(), [])
    distinct = {}
    for c in cand:
        distinct.setdefault(c["key"], c)
    (none if not distinct else one if len(distinct) == 1 else many).append((p, list(distinct.values())))
print("\nsound paths:", len(used_by), "| exactly one clip:", len(one),
      "| several different clips share the name:", len(many), "| no clip:", len(none))
print("\nExamples with several candidates:")
for p, cs in many[:14]:
    print(" ", p, "used by", sorted(used_by[p])[:3])
    for c in cs[:5]:
        print("     ", c["inner"], "pid", c["pid"], c["length"], "s", c["size"], "bytes")
print("\nNo clip found for:", [p for p, _ in none])
