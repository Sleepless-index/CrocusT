# Extract the Spine skeletons, atlases and atlas pages from an unpacked Unity game
# and add the game to the viewer (games.json + games/<id>/game.json).
#   python extract_unity_spine.py <unpacked game folder> <game id> "<Game title>" [viewer dir]
# Example:
#   python extract_unity_spine.py ~/hazel hazelnutlatte "Hazelnut Latte"
import platform, sys, os, re, json, traceback
from unittest.mock import MagicMock

def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "x"

def atlas_pages(text):
    lines = text.splitlines()
    return [lines[i].strip() for i in range(len(lines) - 1)
            if lines[i].strip() and ":" not in lines[i] and lines[i + 1].strip().startswith("size:")]

def rewrite_atlas(text, mapping):
    out = []
    for l in text.splitlines():
        out.append(mapping.get(l.strip(), l))
    return "\n".join(out) + "\n"

def main():
    platform.system = lambda: "Linux"
    sys.platform = "linux"
    for m in ("fmod_toolkit", "fmod_toolkit.libfmod", "pyfmodex"):
        sys.modules[m] = MagicMock()
    import UnityPy

    if len(sys.argv) < 4:
        sys.exit('usage: python extract_unity_spine.py <game folder> <id> "<title>" [viewer dir]')
    root, gid, title = sys.argv[1], sys.argv[2], sys.argv[3]
    viewer = sys.argv[4] if len(sys.argv) > 4 else os.path.expanduser("~/pubpets_archive/viewer")
    datas = [r for r, d, f in os.walk(root) if os.path.basename(r).endswith("_Data")
             and any(x in f for x in ("globalgamemanagers", "data.unity3d"))]
    if not datas:
        sys.exit("No *_Data folder found under " + root)
    DATA = os.path.abspath(datas[0])

    def my_get(*args, **kw):
        path = kw.get("path", args[0] if args else "")
        offset = kw.get("offset", args[-2])
        size = kw.get("size", args[-1])
        with open(os.path.join(DATA, os.path.basename(str(path))), "rb") as fh:
            fh.seek(offset)
            return fh.read(size)
    for name, mod in list(sys.modules.items()):
        if name.startswith("UnityPy") and hasattr(mod, "get_resource_data"):
            setattr(mod, "get_resource_data", my_get)

    pat = re.compile(r"^(level\d+|globalgamemanagers(\.assets)?|resources\.assets|sharedassets\d+\.assets)$")
    files = [os.path.join(DATA, f) for f in sorted(os.listdir(DATA)) if pat.match(f)]
    files += [os.path.join(r, f) for r, _, fs in os.walk(DATA) for f in fs if f.endswith((".bundle", ".unity3d"))]

    skeletons, atlases, textures = {}, {}, {}
    for p in files:
        try:
            env = UnityPy.load(p)
        except Exception:
            continue
        for o in env.objects:
            t = o.type.name
            try:
                if t == "TextAsset":
                    d = o.read()
                    s = d.m_Script
                    b = s.encode("utf-8", "surrogateescape") if isinstance(s, str) else bytes(s)
                    if b[:1] == b"{" and re.search(rb'"spine"\s*:', b[:3000]):
                        skeletons.setdefault(d.m_Name, b)
                    elif b"size:" in b[:600] and b"filter:" in b[:600]:
                        atlases.setdefault(re.sub(r"\.atlas(\.txt)?$", "", d.m_Name), b.decode("utf-8", "replace"))
                elif t == "Texture2D":
                    textures.setdefault(o.read().m_Name.lower(), o)
            except Exception:
                pass
    print("skeletons:", len(skeletons), "| atlases:", len(atlases), "| textures:", len(textures))

    gdir = os.path.join(viewer, "games", gid)
    cgdir = os.path.join(gdir, "cg")
    os.makedirs(cgdir, exist_ok=True)
    used_slugs, ids, no_atlas, no_page, bad_tex, written = set(), {}, [], [], [], set()
    audio_events = []
    for name, b in sorted(skeletons.items()):
        at = atlases.get(name) or next((v for k, v in atlases.items() if k.strip().lower() == name.strip().lower()), None)
        if at is None:
            no_atlas.append(name)
            continue
        sid, n = slug(name), 2
        while sid in used_slugs:
            sid = "%s_%d" % (slug(name), n); n += 1
        used_slugs.add(sid)
        mapping = {}
        for page in atlas_pages(at):
            stem = os.path.splitext(page)[0]
            tex = textures.get(stem.lower())
            ps = slug(stem) + ".png"
            mapping[page] = ps
            if tex is None:
                no_page.append((name, page)); continue
            dest = os.path.join(cgdir, ps)
            if ps in written:
                continue
            try:
                tex.read().image.save(dest)
                written.add(ps)
            except Exception:
                bad_tex.append((name, page, traceback.format_exc().splitlines()[-1]))
        open(os.path.join(cgdir, sid + ".json"), "wb").write(b)
        open(os.path.join(cgdir, sid + ".atlas"), "w", encoding="utf-8").write(rewrite_atlas(at, mapping))
        ids[sid] = name
        try:
            ev = json.loads(b).get("events", {})
            audio_events += [(name, k, v.get("audio")) for k, v in ev.items() if v.get("audio")]
        except Exception:
            pass
    print("added", len(ids), "skeletons | atlas pages written:", len(written))
    print("no atlas for:", no_atlas)
    print("pages with no texture:", no_page[:8])
    print("texture decode failures:", bad_tex[:5])
    print("spine events that name an audio file:", len(audio_events), audio_events[:6])

    def key(n):
        m = re.match(r"(\d+)", n)
        return (0, int(m.group(1)), n.lower()) if m else (1, 0, n.lower())
    scenes = [s for s, n in ids.items() if re.match(r"\d", n)]
    others = [s for s in ids if s not in scenes]
    groups = []
    for gname, members in (("Scenes", scenes), ("Characters", others)):
        if members:
            members.sort(key=lambda s: key(ids[s]))
            groups.append({"name": gname, "items": [{"id": s, "title": ids[s]} for s in members]})
    with open(os.path.join(gdir, "game.json"), "w") as fh:
        json.dump({"title": title, "groups": groups}, fh, indent=1)
    gp = os.path.join(viewer, "games.json")
    games = json.load(open(gp)) if os.path.exists(gp) else []
    games = [g for g in games if g.get("id") != gid]
    games.append({"id": gid, "title": title, "path": "games/" + gid, "runtime": "spine-webgl.js", "cover": ""})
    with open(gp, "w") as fh:
        json.dump(games, fh, indent=1)
    print("wrote", os.path.join(gdir, "game.json"), "and updated games.json")

if __name__ == "__main__":
    main()
