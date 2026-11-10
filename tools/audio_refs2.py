# Fourth pass: the game's scripts have no type info, so read their raw bytes
# and look for references (PPtr) to AudioClips, with the nearest name string.
# Run from the folder that contains "assets":  python audio_refs2.py
import platform, sys, os, json, struct, collections
from unittest.mock import MagicMock
platform.system = lambda: "Linux"
sys.platform = "linux"
for m in ("fmod_toolkit", "fmod_toolkit.libfmod", "pyfmodex"):
    sys.modules[m] = MagicMock()
import UnityPy

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
            clip[(iname(o), o.path_id)] = o.read().m_Name
        elif t == "MonoScript":
            script[(iname(o), o.path_id)] = o.read().m_ClassName
        elif t == "GameObject":
            gobj[(iname(o), o.path_id)] = o.read().m_Name
    except Exception:
        pass
print(len(clip), "clips,", len(script), "scripts,", len(gobj), "game objects")

def prev_str(raw, p):
    for L in range(1, 81):
        q = p - 4 - ((L + 3) & ~3)
        if q < 0:
            break
        if struct.unpack_from("<i", raw, q)[0] == L:
            s = raw[q + 4:q + 4 + L]
            if all(32 <= c < 127 for c in s):
                return s.decode()
    return None

rows = []
for o in objs:
    if o.type.name != "MonoBehaviour":
        continue
    try:
        raw = bytes(o.get_raw_data())
    except Exception:
        continue
    if len(raw) < 28:
        continue
    gf, gp = struct.unpack_from("<iq", raw, 0)
    sf, sp = struct.unpack_from("<iq", raw, 16)
    hits = []
    for p in range(0, len(raw) - 11, 4):
        fid, pid = struct.unpack_from("<iq", raw, p)
        if 0 <= fid < 8 and 0 < pid < 100000:
            k = resolve(o, fid, pid)
            if k in clip:
                hits.append((p, prev_str(raw, p), clip[k]))
    if len(hits) >= 2:
        rows.append(dict(file=iname(o), pid=o.path_id, size=len(raw),
                         script=script.get(resolve(o, sf, sp), "?"),
                         go=gobj.get(resolve(o, gf, gp), "?"), hits=hits))
json.dump(rows, open("audio_refs2.json", "w", encoding="utf-8"), ensure_ascii=False)

agg = collections.defaultdict(lambda: [0, 0])
for r in rows:
    agg[r["script"]][0] += 1
    agg[r["script"]][1] += len(r["hits"])
print("\nscripts with audio references (script: objects, total refs):")
for s, (n, m) in sorted(agg.items(), key=lambda x: -x[1][1])[:10]:
    print(" ", s, n, m)
print("\nlargest examples:")
for r in sorted(rows, key=lambda r: -len(r["hits"]))[:4]:
    print(" ", r["file"], r["script"], "on", r["go"], "-", len(r["hits"]), "refs")
    for p, nm, cn in r["hits"][:10]:
        print("     ", p, nm, "->", cn)

print("\nAudioSource components (game object -> clip):")
n = 0
for o in objs:
    if o.type.name != "AudioSource":
        continue
    try:
        d = o.read()
        c = d.m_audioClip
        ck = resolve(o, getattr(c, "file_id", 0), getattr(c, "path_id", 0))
        g = d.m_GameObject
        gk = resolve(o, getattr(g, "file_id", 0), getattr(g, "path_id", 0))
        if ck in clip:
            n += 1
            if n <= 15:
                print(" ", iname(o), gobj.get(gk, "?"), "->", clip[ck])
    except Exception:
        pass
print(" ", n, "audio sources use a clip")
print("wrote audio_refs2.json")
