# Third pass: finds which game objects/scripts reference which AudioClips,
# so we can tell Alice's "102" from Hetty's "102".
# Run from the folder that contains "assets":  python audio_refs.py
import platform, sys, os, json, collections
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

def resolve(o, p):
    fid, pid = p.get("m_FileID", 0), p.get("m_PathID", 0)
    if not pid:
        return None
    if fid == 0:
        return (iname(o), pid)
    ext = getattr(o.assets_file, "externals", [])
    if fid - 1 < len(ext):
        return (os.path.basename(str(getattr(ext[fid - 1], "path", ""))).lower(), pid)
    return None

def walk(o, node, path, refs, strs):
    if isinstance(node, dict):
        if "m_FileID" in node and "m_PathID" in node:
            k = resolve(o, node)
            if k in clip:
                refs.append((path, clip[k], k))
            return
        for a, b in node.items():
            walk(o, b, path + "." + str(a), refs, strs)
    elif isinstance(node, list):
        for i, b in enumerate(node):
            walk(o, b, path + "[" + str(i) + "]", refs, strs)
    elif isinstance(node, str) and ("GAME/" in node or "_Game_" in node):
        strs.append((path, node))

rows, fails, strrows = [], 0, []
for o in objs:
    if o.type.name != "MonoBehaviour":
        continue
    try:
        tree = o.read_typetree()
    except Exception:
        fails += 1
        continue
    refs, strs = [], []
    walk(o, tree, "", refs, strs)
    sc = "?"
    if isinstance(tree.get("m_Script"), dict):
        k = resolve(o, tree["m_Script"])
        sc = script.get(k, "?")
    go = "?"
    if isinstance(tree.get("m_GameObject"), dict):
        k = resolve(o, tree["m_GameObject"])
        go = gobj.get(k, "?")
    if refs:
        rows.append(dict(file=iname(o), pid=o.path_id, script=sc, go=go, refs=[(a, b) for a, b, _ in refs]))
    if strs:
        strrows.append(dict(file=iname(o), script=sc, go=go, strs=strs[:5]))
print("typetree failed on", fails, "scripts")
json.dump(rows, open("audio_refs.json", "w", encoding="utf-8"), ensure_ascii=False)

agg = collections.defaultdict(lambda: [0, 0])
for r in rows:
    agg[r["script"]][0] += 1
    agg[r["script"]][1] += len(r["refs"])
print("\nscripts that reference audio clips (script: objects, total clip refs):")
for s, (n, m) in sorted(agg.items(), key=lambda x: -x[1][1])[:10]:
    print(" ", s, n, m)
print("\nlargest examples:")
for r in sorted(rows, key=lambda r: -len(r["refs"]))[:4]:
    print(" ", r["file"], r["script"], "on", r["go"], "-", len(r["refs"]), "clips")
    for a, b in r["refs"][:8]:
        print("     ", a, "->", b)
print("\nstrings that look like sound paths:", len(strrows))
for r in strrows[:8]:
    print(" ", r["file"], r["script"], r["go"], r["strs"][:2])
print("wrote audio_refs.json")
