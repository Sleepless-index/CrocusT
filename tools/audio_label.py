# Sixth pass: label the DialogSystem voice runs by girl, using the table
# AudioSources (whose object names end in _Alice / _Hetty / _Anto) as anchors,
# then map each spine sound path to one clip. Writes audio_map.json.
# Run from the folder that contains "assets":  python audio_label.py [viewer/cg dir]
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

clip, script, gobj = {}, {}, {}
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
        elif t == "GameObject":
            gobj[(iname(o), o.path_id)] = o.read().m_Name
    except Exception:
        pass
print(len(clip), "clips")

# anchors: table AudioSources whose object name ends with a girl's name
label = {}
suffixes = collections.Counter()
for o in objs:
    if o.type.name != "AudioSource":
        continue
    try:
        d = o.read()
        c, g = d.m_audioClip, d.m_GameObject
        ck = resolve(o, getattr(c, "file_id", 0), getattr(c, "path_id", 0))
        gn = gobj.get(resolve(o, getattr(g, "file_id", 0), getattr(g, "path_id", 0)), "")
        mm = re.search(r"_(Alice|Hetty|Anto\w*)$", gn)
        if ck in clip and mm:
            label[ck] = mm.group(1)
            suffixes[mm.group(1)] += 1
    except Exception:
        pass
print("anchor clips by girl:", dict(suffixes))

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
                seq.append((p, k))
if not seq:
    sys.exit("No voice references found - run this from the folder that contains assets")

runs, cur = [], []
for p, k in seq:
    if cur and p - cur[-1][0] != 12:
        runs.append(cur); cur = []
    cur.append((p, k))
runs.append(cur)

rl = []
conflicts = 0
for r in runs:
    cnt = collections.Counter(label[k] for _, k in r if k in label)
    if len(cnt) > 1:
        conflicts += 1
    rl.append(cnt.most_common(1)[0][0] if cnt else None)
before = sum(1 for x in rl if x)
for i in range(1, len(rl) - 1):
    if rl[i] is None:
        a = next((rl[j] for j in range(i - 1, -1, -1) if rl[j]), None)
        b = next((rl[j] for j in range(i + 1, len(rl)) if rl[j]), None)
        if a and a == b:
            rl[i] = a
print(len(runs), "runs | labelled by anchors:", before, "| after filling gaps:", sum(1 for x in rl if x),
      "| runs with mixed anchors:", conflicts)
print("runs per girl:", dict(collections.Counter(x for x in rl if x)))

by_girl = collections.defaultdict(list)
for r, g in zip(runs, rl):
    if g:
        for _, k in r:
            by_girl[g].append(clip[k])

need = collections.defaultdict(set)
others_need = set()
for f in glob.glob(os.path.join(cg_dir, "*.json")):
    try:
        ev = json.load(open(f, encoding="utf-8")).get("events", {})
    except Exception:
        continue
    for v in ev.values():
        a = v.get("audio", "")
        mm = re.match(r"AVG/(.+)/GAME/(\d+)\.\w+$", a)
        if mm:
            need[mm.group(1)].add(int(mm.group(2)))
        elif a:
            others_need.add(a)

def girl_for(folder):
    if folder == "Anto_2":
        return "Anto2" if "Anto2" in by_girl else "Anto"
    return folder

voice, ambiguous, missing = {}, {}, []
print("\nvoice lines per folder (resolved / ambiguous / missing):")
for folder, nums in sorted(need.items()):
    g = girl_for(folder)
    ok = amb = miss = 0
    for n in sorted(nums):
        c = [x for x in by_girl.get(g, []) if x["name"].isdigit() and int(x["name"]) == n]
        key = "AVG/%s/GAME/%03d" % (folder, n)
        if len(c) == 1:
            voice[key] = c[0]; ok += 1
        elif c:
            ambiguous[key] = c; amb += 1
        else:
            missing.append(key); miss += 1
    print(" ", folder, "(girl label %s):" % g, ok, "/", amb, "/", miss, "of", len(nums))

by_name = collections.defaultdict(list)
for c in clip.values():
    by_name[c["name"].lower()].append(c)
effects, bad = {}, []
for a in sorted(others_need):
    c = by_name.get(os.path.splitext(os.path.basename(a))[0].lower(), [])
    if len(c) == 1:
        effects[a] = c[0]
    else:
        bad.append((a, len(c)))
print("effects resolved:", len(effects), "| unresolved:", bad)
print("missing voice lines:", missing[:12])
print("example ambiguous:", [(k, [(x["file"], x["length"]) for x in v]) for k, v in list(ambiguous.items())[:3]])
json.dump({"voice": voice, "ambiguous": ambiguous, "effects": effects}, open("audio_map.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("wrote audio_map.json")
