# Fifth pass: the DialogSystem script holds one long list of voice clips.
# Split it into runs (one folder each), label each run using the numbers the
# spine events need, and write audio_map.json (sound path -> exact clip).
# Run from the folder that contains "assets":  python audio_runs.py [viewer/cg dir]
import platform, sys, os, json, glob, re, struct, collections
from unittest.mock import MagicMock
platform.system = lambda: "Linux"
sys.platform = "linux"
for m in ("fmod_toolkit", "fmod_toolkit.libfmod", "pyfmodex"):
    sys.modules[m] = MagicMock()
import UnityPy

cg_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/pubpets_archive/viewer/cg")

objs = []
for root, _, files in os.walk("assets"):
    for f in files:
        if f.endswith((".dat", ".json", ".resource")) or f == "boot.config":
            continue
        try:
            objs.extend(UnityPy.load(os.path.join(root, f)).objects)
        except Exception:
            pass

def iname(o):
    return os.path.basename(str(getattr(o.assets_file, "name", "?"))).lower()

def resolve(o, fid, pid):
    if not pid:
        return None
    if fid == 0:
        return (iname(o), pid)
    ext = getattr(o.assets_file, "externals", [])
    if 0 < fid <= len(ext):
        return (os.path.basename(str(getattr(ext[fid - 1], "path", ""))).lower(), pid)
    return None

clip, script = {}, {}
for o in objs:
    t = o.type.name
    try:
        if t == "AudioClip":
            d = o.read()
            r = getattr(d, "m_Resource", None)
            clip[(iname(o), o.path_id)] = dict(
                file=iname(o), pid=o.path_id, name=d.m_Name,
                length=round(getattr(d, "m_Length", 0) or 0, 2),
                freq=getattr(d, "m_Frequency", 0), ch=getattr(d, "m_Channels", 0),
                fmt=getattr(d, "m_CompressionFormat", 0),
                src=getattr(r, "m_Source", "") if r else "",
                off=getattr(r, "m_Offset", 0) if r else 0,
                size=getattr(r, "m_Size", 0) if r else 0)
        elif t == "MonoScript":
            script[(iname(o), o.path_id)] = o.read().m_ClassName
    except Exception:
        pass
print(len(clip), "clips")

seq = []
for o in objs:
    if o.type.name != "MonoBehaviour":
        continue
    try:
        raw = bytes(o.get_raw_data())
        sf, sp = struct.unpack_from("<iq", raw, 16)
    except Exception:
        continue
    if script.get(resolve(o, sf, sp)) != "DialogSystem":
        continue
    for p in range(0, len(raw) - 11, 4):
        fid, pid = struct.unpack_from("<iq", raw, p)
        if 0 <= fid < 8 and 0 < pid < 100000:
            k = resolve(o, fid, pid)
            if k in clip:
                seq.append((p, clip[k]))
print(len(seq), "voice references in DialogSystem")

def num(c):
    return int(c["name"]) if c["name"].isdigit() else None

runs, cur, why = [], [], []
for p, c in seq:
    if cur:
        pp, pc = cur[-1]
        n, pn = num(c), num(pc)
        brk = None
        if p - pp != 12: brk = "array gap"
        elif n is None or pn is None or n <= pn: brk = "number reset"
        if brk:
            runs.append(cur); why.append(brk); cur = []
    cur.append((p, c))
if cur:
    runs.append(cur); why.append("end")
print(len(runs), "runs")
if not runs:
    sys.exit("No voice references found - run this from the folder that contains assets")
need = collections.defaultdict(set)
for f in glob.glob(os.path.join(cg_dir, "*.json")):
    try:
        ev = json.load(open(f, encoding="utf-8")).get("events", {})
    except Exception:
        continue
    for v in ev.values():
        mm = re.match(r"(AVG/.+/GAME)/(\d+)\.\w+$", v.get("audio", ""))
        if mm:
            need[mm.group(1)].add(int(mm.group(2)))

assign = {}
for folder, nums in sorted(need.items()):
    best = max(range(len(runs)), key=lambda i: sum(1 for _, c in runs[i] if num(c) in nums))
    score = sum(1 for _, c in runs[best] if num(c) in nums)
    assign[folder] = (best, score)
print("\nfolder -> run (needed numbers found / needed):")
for folder, (i, s) in assign.items():
    print(" ", folder, "-> run", i, ":", s, "/", len(need[folder]))
print("\nruns:")
for i, r in enumerate(runs[:40]):
    ns = [num(c) for _, c in r if num(c) is not None]
    tag = [f for f, (j, _) in assign.items() if j == i]
    print(" ", i, "len", len(r), "numbers", (min(ns), max(ns)) if ns else "-", "ended by", why[i], tag or "")

out, bad = {}, []
for folder, nums in need.items():
    ri = assign[folder][0]
    for n in sorted(nums):
        c = [c for _, c in runs[ri] if num(c) == n]
        key = "%s/%03d" % (folder, n)
        if len(c) == 1:
            out[key] = c[0]
        else:
            bad.append((key, len(c)))
by_name = collections.defaultdict(list)
for c in clip.values():
    by_name[c["name"].lower()].append(c)
others = {}
for f in glob.glob(os.path.join(cg_dir, "*.json")):
    try:
        ev = json.load(open(f, encoding="utf-8")).get("events", {})
    except Exception:
        continue
    for v in ev.values():
        p = v.get("audio", "")
        if p and not re.match(r"AVG/.+/GAME/\d+", p):
            c = by_name.get(os.path.splitext(os.path.basename(p))[0].lower(), [])
            if len(c) == 1:
                others[p] = c[0]
            else:
                bad.append((p, len(c)))
json.dump({"voice": out, "effects": others}, open("audio_map.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\nresolved voice lines:", len(out), "| resolved effects:", len(others), "| unresolved:", len(bad))
print("unresolved:", bad[:20])
print("wrote audio_map.json")
