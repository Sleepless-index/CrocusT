# Final pass: extract the sounds the spine events use and convert them to .ogg.
# The game's AudioManager lists the effects, then the CG voice lines in the order
# Anto, Hetty, Alice - that order is what tells the girls apart.
# Needs: pkg install libvorbis libogg   and   pip install fsb5
# Run from the folder that contains "assets":
#   python audio_extract.py [viewer/cg dir] [output audio dir]
import platform, sys, os, json, glob, re, struct, collections, traceback
from unittest.mock import MagicMock

GIRL_RUN = {"Anto": 0, "Hetty": 1, "Alice": 2}

def split_runs(named):
    """named = ordered [(name, clip)]. Numeric tail is split where numbers stop rising."""
    tail = [(n, c) for n, c in named if n.isdigit()]
    runs, cur = [], []
    for n, c in tail:
        if cur and int(n) <= int(cur[-1][0]):
            runs.append(cur); cur = []
        cur.append((n, c))
    if cur:
        runs.append(cur)
    return runs

def main():
    platform.system = lambda: "Linux"
    sys.platform = "linux"
    for m in ("fmod_toolkit", "fmod_toolkit.libfmod", "pyfmodex"):
        sys.modules[m] = MagicMock()
    import ctypes.util, glob as g2
    orig = ctypes.util.find_library
    def find(name):
        r = orig(name)
        if r:
            return r
        for d in (os.environ.get("PREFIX", "") + "/lib", "/usr/lib", "/usr/local/lib"):
            c = sorted(g2.glob(os.path.join(d, "lib%s.so*" % name)))
            if c:
                return c[0]
        return None
    ctypes.util.find_library = find
    import UnityPy
    import fsb5

    cg_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/pubpets_archive/viewer/cg")
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser("~/pubpets_archive/viewer/audio")

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
                    src=getattr(r, "m_Source", "") if r else "",
                    off=getattr(r, "m_Offset", 0) if r else 0,
                    size=getattr(r, "m_Size", 0) if r else 0)
            elif t == "MonoScript":
                script[(iname(o), o.path_id)] = o.read().m_ClassName
        except Exception:
            pass
    print(len(clip), "clips")

    best = []
    for o in objs:
        if o.type.name != "MonoBehaviour":
            continue
        try:
            raw = bytes(o.get_raw_data())
            sf, sp = struct.unpack_from("<iq", raw, 16)
        except Exception:
            continue
        if script.get(resolve(o, sf, sp)) != "AudioManager":
            continue
        hits = []
        for p in range(0, len(raw) - 11, 4):
            fid, pid = struct.unpack_from("<iq", raw, p)
            if 0 <= fid < 8 and 0 < pid < 100000:
                k = resolve(o, fid, pid)
                if k in clip:
                    hits.append((clip[k]["name"], clip[k]))
        if len(hits) > len(best):
            best = hits
    if not best:
        sys.exit("AudioManager list not found - run this from the folder that contains assets")
    runs = split_runs(best)
    print("AudioManager:", len(best), "clips;", "voice runs:", [len(r) for r in runs])
    effects = {}
    for n, c in best:
        if not n.isdigit():
            effects.setdefault(n.lower(), c)
    voice = {}
    if len(runs) == 3:
        for girl, i in GIRL_RUN.items():
            voice[girl] = {int(n): c for n, c in runs[i]}
    else:
        print("Expected 3 voice runs, so voice lines are skipped")

    assign, conflicts, unresolved = {}, [], []
    for f in sorted(glob.glob(os.path.join(cg_dir, "*.json"))):
        try:
            ev = json.load(open(f, encoding="utf-8")).get("events", {})
        except Exception:
            continue
        for ename, v in ev.items():
            a = v.get("audio", "")
            if not a:
                continue
            mv = re.search(r"/GAME/(\d+)\.\w+$", a)
            if mv:
                gm = re.search(r"_(Alice|Hetty|Anto)_", ename)
                c = voice.get(gm.group(1), {}).get(int(mv.group(1))) if gm else None
            else:
                c = effects.get(os.path.splitext(os.path.basename(a))[0].lower())
            if c is None:
                unresolved.append((os.path.basename(f), ename, a))
            elif a in assign and (assign[a]["file"], assign[a]["pid"]) != (c["file"], c["pid"]):
                conflicts.append((a, ename))
            else:
                assign[a] = c
    print("sound paths resolved:", len(assign), "| conflicts:", len(conflicts), "| unresolved:", len(unresolved))
    print("unresolved:", sorted({u[2] for u in unresolved})[:10])
    print("conflicts:", conflicts[:5])

    ok, bad, first_err, manifest = 0, 0, None, {}
    for a, c in sorted(assign.items()):
        try:
            with open(os.path.join("assets/bin/Data", c["src"]), "rb") as fh:
                fh.seek(c["off"])
                data = fh.read(c["size"])
            fsb = fsb5.FSB5(data)
            ext = fsb.get_sample_extension()
            blob = fsb.rebuild_sample(fsb.samples[0])
            dest = os.path.join(out_dir, os.path.splitext(a)[0] + "." + ext)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as fh:
                fh.write(blob)
            manifest[a] = dict(clip=c["name"], length=c["length"], file=os.path.relpath(dest, out_dir))
            ok += 1
        except Exception:
            bad += 1
            if first_err is None:
                first_err = traceback.format_exc()
    json.dump(manifest, open(os.path.join(out_dir, "manifest.json"), "w"), indent=1) if ok else None
    print("converted:", ok, "| failed:", bad)
    if first_err:
        print("first error:\n" + first_err)
    print("output folder:", out_dir)

if __name__ == "__main__":
    main()
