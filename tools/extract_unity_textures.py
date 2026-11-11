# Extract the large Texture2D images from an unpacked Unity game as .webp plus small
# thumbnails and add the game to the viewer (games.json + games/<id>/game.json +
# games/<id>/images.json). For games with no Spine data and no cg_epNN_NN naming.
# Textures are grouped into tabs by the first word of their name (Nora_CG_Cafe -> Nora)
# and numbered/lettered frames of the same name are grouped as variants of one item.
#   python extract_unity_textures.py <unpacked game folder> <game id> "<Game title>" [viewer dir] [options]
# Options:
#   --min-w N       skip textures narrower than N px (default 1000)
#   --min-h N       skip textures shorter than N px (default 560)
#   --match REGEX   only keep textures whose name matches (case-insensitive)
#   --skip REGEX    drop textures whose name matches (case-insensitive)
#   --tabs A,B,C    make one tab per name listed (first listed that matches wins); everything
#                   else goes to "Other". Matches CamelCase words: Au matches CasaAuExt, not Aurora
#   --list          only print the groups that would be made, write nothing
# Example:
#   python extract_unity_textures.py ~/bb bb "Between Beasts" viewer --tabs Alexa,Ashe,Lily,Nora,Mara,Rox
import platform, sys, os, re, json, collections
from unittest.mock import MagicMock


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "x"


def natkey(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s.lower())]


def pretty(s):
    return re.sub(r"\s+", " ", re.sub(r"[_\-]+", " ", s)).strip()


def base_of(name):
    """Alexa_Halloween11 -> Alexa_Halloween, cg_03b -> cg, Nora_Spank_2 -> Nora_Spank"""
    b = re.sub(r"[\s_\-.]*\d+[a-z]?$", "", name, flags=re.I).strip("_- .")
    return b or name


def tab_of(name):
    """first word of the name with digits stripped: Dia13_Alexa_P -> Dia, Nora_CG_Cafe -> Nora"""
    w = re.split(r"[_\-\s.]+", name.strip())[0]
    w = re.sub(r"\d+$", "", w) or w
    return w[:1].upper() + w[1:]


def tab_from_list(name, wanted):
    for w in wanted:
        if re.search(r"(?:^|[^A-Za-z]|(?<=[a-z]))" + re.escape(w) + r"(?![a-z])", name):
            return w
    return "Other"


def build_catalog(entries, min_items=6, wanted=None):
    """entries: [(name, filename)] -> images.json groups. Small tabs are merged into 'Other'.
    With wanted=[names], tabs are exactly those names plus 'Other'."""
    tabs = collections.defaultdict(lambda: collections.defaultdict(list))
    for name, fn in entries:
        t = tab_from_list(name, wanted) if wanted else tab_of(name)
        tabs[t][base_of(name)].append((name, fn))
    if wanted:
        min_items = 0
    small = [t for t, b in tabs.items() if sum(len(v) for v in b.values()) < min_items]
    if len(small) > 1:
        other = tabs.setdefault("Other", collections.defaultdict(list))
        for t in small:
            if t == "Other":
                continue
            for b, v in tabs.pop(t).items():
                other[b] += v
    catalog = []
    for t in sorted(tabs, key=lambda x: (x == "Other", natkey(x))):
        items = []
        for b in sorted(tabs[t], key=natkey):
            vs = sorted(tabs[t][b], key=lambda x: natkey(x[0]))
            items.append({"id": slug(t + "_" + b), "title": pretty(b),
                          "thumb": "img/th/" + vs[0][1], "images": ["img/" + v[1] for v in vs]})
        catalog.append({"name": t, "items": items})
    return catalog


def find_data(root):
    datas = [r for r, d, f in os.walk(root) if os.path.basename(r).endswith("_Data")
             and any(x in f for x in ("globalgamemanagers", "data.unity3d"))]
    if not datas:
        sys.exit("No *_Data folder found under " + root)
    return os.path.abspath(datas[0])


def main():
    platform.system = lambda: "Linux"
    sys.platform = "linux"
    for m in ("fmod_toolkit", "fmod_toolkit.libfmod", "pyfmodex"):
        sys.modules[m] = MagicMock()
    import UnityPy
    from PIL import Image

    args, pos, opts, only_list = sys.argv[1:], [], {"--min-w": 1000, "--min-h": 560, "--match": None, "--skip": None, "--tabs": None}, False
    i = 0
    while i < len(args):
        a = args[i]
        if a in opts:
            opts[a] = int(args[i + 1]) if a.startswith("--min") else args[i + 1]; i += 2; continue
        if a == "--list":
            only_list = True
        else:
            pos.append(a)
        i += 1
    if len(pos) < 3:
        sys.exit('usage: python extract_unity_textures.py <game folder> <id> "<title>" [viewer dir] '
                 "[--min-w N] [--min-h N] [--match RE] [--skip RE] [--tabs A,B,C] [--list]")
    root, gid, title = pos[:3]
    viewer = pos[3] if len(pos) > 3 else os.path.expanduser("~/pubpets_archive/viewer")
    DATA = find_data(root)

    def my_get(*a, **kw):
        path = kw.get("path", a[0] if a else "")
        offset = kw.get("offset", a[-2])
        size = kw.get("size", a[-1])
        with open(os.path.join(DATA, os.path.basename(str(path))), "rb") as fh:
            fh.seek(offset)
            return fh.read(size)
    for name, mod in list(sys.modules.items()):
        if name.startswith("UnityPy") and hasattr(mod, "get_resource_data"):
            setattr(mod, "get_resource_data", my_get)

    pat = re.compile(r"^(level\d+|globalgamemanagers(\.assets)?|resources\.assets|sharedassets\d+\.assets)$")
    files = [os.path.join(DATA, f) for f in sorted(os.listdir(DATA)) if pat.match(f)]
    files += [os.path.join(r, f) for r, _, fs in os.walk(DATA) for f in fs if f.endswith((".bundle", ".unity3d"))]
    match = re.compile(opts["--match"], re.I) if opts["--match"] else None
    skip = re.compile(opts["--skip"], re.I) if opts["--skip"] else None

    objs, small, filtered = {}, 0, 0
    for p in files:
        try:
            env = UnityPy.load(p)
        except Exception:
            continue
        for o in env.objects:
            if o.type.name != "Texture2D":
                continue
            try:
                d = o.read()
                n = d.m_Name
                if n.lower() in objs:
                    continue
                if d.m_Width < opts["--min-w"] or d.m_Height < opts["--min-h"]:
                    small += 1; continue
            except Exception:
                continue
            if (match and not match.search(n)) or (skip and skip.search(n)):
                filtered += 1; continue
            objs[n.lower()] = (n, o)
    print("kept %d textures | too small: %d | filtered by --match/--skip: %d" % (len(objs), small, filtered))

    names = sorted((v[0] for v in objs.values()), key=natkey)
    fns = {}
    for n in names:
        fn, k = slug(n) + ".webp", 2
        while fn in fns.values():
            fn = "%s_%d.webp" % (slug(n), k); k += 1
        fns[n] = fn
    wanted = [t.strip() for t in opts["--tabs"].split(",") if t.strip()] if opts["--tabs"] else None
    catalog = build_catalog([(n, fns[n]) for n in names], wanted=wanted)
    print("tabs:", [(g["name"], len(g["items"]), sum(len(i["images"]) for i in g["items"])) for g in catalog])
    if only_list or not names:
        print("(nothing written)" if only_list else "Nothing kept. Lower --min-w / --min-h.")
        return

    gdir = os.path.join(viewer, "games", gid)
    imgdir, thdir = os.path.join(gdir, "img"), os.path.join(gdir, "img", "th")
    os.makedirs(thdir, exist_ok=True)
    total, failed, done, written = 0, [], 0, set()
    for n in names:
        fn = fns[n]
        try:
            im = objs[n.lower()][1].read().image
            alpha = im.mode in ("RGBA", "LA") and im.getchannel("A").getextrema()[0] < 255
            im.convert("RGBA" if alpha else "RGB").save(os.path.join(imgdir, fn), "WEBP", quality=88)
            th = im.convert("RGB")
            th.thumbnail((480, 480))
            th.save(os.path.join(thdir, fn), "WEBP", quality=78)
            total += os.path.getsize(os.path.join(imgdir, fn))
            written.add(fn)
        except Exception as e:
            failed.append((n, str(e)[:60]))
        done += 1
        if done % 50 == 0:
            print("  %d / %d" % (done, len(names)))
    # drop entries whose image could not be written
    for g in catalog:
        for it in g["items"]:
            it["images"] = [x for x in it["images"] if os.path.basename(x) in written]
            it["thumb"] = "img/th/" + os.path.basename(it["images"][0]) if it["images"] else ""
        g["items"] = [it for it in g["items"] if it["images"]]
    catalog = [g for g in catalog if g["items"]]
    print("written: %d | failed: %d %s | total size: %.0f MB" % (len(written), len(failed), failed[:5], total / 1e6))

    with open(os.path.join(gdir, "images.json"), "w") as fh:
        json.dump({"groups": catalog}, fh, indent=1)
    with open(os.path.join(gdir, "game.json"), "w") as fh:
        json.dump({"title": title, "groups": []}, fh, indent=1)
    gp = os.path.join(viewer, "games.json")
    games = json.load(open(gp)) if os.path.exists(gp) else []
    games = [g for g in games if g.get("id") != gid]
    cover = catalog[0]["items"][0]["thumb"] if catalog else ""
    games.append({"id": gid, "title": title, "path": "games/" + gid, "runtime": "spine-webgl.js",
                  "cover": "games/%s/%s" % (gid, cover) if cover else ""})
    with open(gp, "w") as fh:
        json.dump(games, fh, indent=1)
    print("wrote", os.path.join(gdir, "images.json"), "and updated games.json")


if __name__ == "__main__":
    main()
