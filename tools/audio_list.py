# Lists every AudioClip in the unpacked APK and matches them to the sound
# paths used by the spine events. Run from the folder that contains "assets".
#   python audio_list.py [path/to/viewer/cg]
import platform, sys, os, json, glob, collections
from unittest.mock import MagicMock
platform.system = lambda: "Linux"
sys.platform = "linux"
for m in ("fmod_toolkit", "fmod_toolkit.libfmod", "pyfmodex"):
    sys.modules[m] = MagicMock()
import UnityPy

cg_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/pubpets_archive/viewer/cg")

clips, container = [], {}
for root, _, files in os.walk("assets"):
    for f in files:
        if f.endswith((".dat", ".json", ".resource")) or f == "boot.config":
            continue
        try:
            env = UnityPy.load(os.path.join(root, f))
        except Exception:
            continue
        for o in env.objects:
            t = o.type.name
            try:
                if t == "AudioClip":
                    d = o.read()
                    r = getattr(d, "m_Resource", None)
                    clips.append(dict(
                        file=f, pid=o.path_id, name=getattr(d, "m_Name", ""),
                        ch=getattr(d, "m_Channels", ""), freq=getattr(d, "m_Frequency", ""),
                        length=round(getattr(d, "m_Length", 0) or 0, 2),
                        fmt=getattr(d, "m_CompressionFormat", ""),
                        src=getattr(r, "m_Source", "") if r else "",
                        off=getattr(r, "m_Offset", "") if r else "",
                        size=getattr(r, "m_Size", "") if r else ""))
                elif t == "ResourceManager":
                    d = o.read()
                    items = d.m_Container.items() if hasattr(d.m_Container, "items") else d.m_Container
                    for k, v in items:
                        pid = getattr(v, "path_id", None)
                        if pid:
                            container.setdefault(pid, k)
            except Exception as e:
                print("skip", t, e)

for c in clips:
    c["path"] = container.get(c["pid"], "")

with open("audio_list.tsv", "w", encoding="utf-8") as fh:
    cols = ["file", "pid", "name", "ch", "freq", "length", "fmt", "src", "off", "size", "path"]
    fh.write("\t".join(cols) + "\n")
    for c in clips:
        fh.write("\t".join(str(c[k]) for k in cols) + "\n")

names = collections.Counter(c["name"] for c in clips)
dups = {n: k for n, k in names.items() if k > 1}
print(len(clips), "clips,", len(names), "unique names,", len(dups), "names used more than once")
print(sum(1 for c in clips if c["path"]), "clips have a Resources path")
print("sample names:", [c["name"] for c in clips[:15]])
print("sample paths:", [c["path"] for c in clips if c["path"]][:8])

needed = set()
for f in glob.glob(os.path.join(cg_dir, "*.json")):
    try:
        ev = json.load(open(f, encoding="utf-8")).get("events", {})
    except Exception:
        continue
    for v in ev.values():
        if v.get("audio"):
            needed.add(v["audio"])
print(len(needed), "distinct sound paths used by spine events")

by_path = {os.path.splitext(c["path"])[0].lower(): c for c in clips if c["path"]}
by_name = collections.defaultdict(list)
for c in clips:
    by_name[c["name"].lower()].append(c)
hit_path = hit_name = 0
miss = collections.Counter()
for p in sorted(needed):
    stem = os.path.splitext(p)[0]
    if stem.lower() in by_path:
        hit_path += 1
    elif os.path.basename(stem).lower() in by_name:
        hit_name += 1
    else:
        miss[os.path.dirname(p)] += 1
print("matched by full path:", hit_path, "| matched by name only:", hit_name, "| not found:", sum(miss.values()))
for d, n in miss.most_common():
    print("  not found in", d, ":", n)
print("wrote audio_list.tsv")
