# Extract the full-size still images (CGs, backgrounds, pin-ups, legacy and concept art)
# from an unpacked Unity game as .webp plus small thumbnails, and write images.json
# for the viewer.
#   python extract_unity_images.py <unpacked game folder> <game id> [viewer dir]
import platform, sys, os, re, json, collections
from unittest.mock import MagicMock

NAME = re.compile(r"^(cg|bg|pinup|legacy|concept)_ep(\d+)_(\d+)([a-z]?)$", re.I)
KINDS = {"cg": "CG", "bg": "Backgrounds", "pinup": "Pin-ups", "legacy": "Legacy", "concept": "Concept art"}

def group(names):
    """names -> {(kind, ep): {num: [(letter, name)]}} sorted."""
    out = collections.defaultdict(lambda: collections.defaultdict(list))
    for n in names:
        m = NAME.match(n)
        if m:
            k, ep, num, letter = m.group(1).lower(), int(m.group(2)), int(m.group(3)), m.group(4).lower()
            out[(k, ep)][num].append((letter, n))
    return out

def main():
    platform.system = lambda: "Linux"
    sys.platform = "linux"
    for m in ("fmod_toolkit", "fmod_toolkit.libfmod", "pyfmodex"):
        sys.modules[m] = MagicMock()
    import UnityPy

    if len(sys.argv) < 3:
        sys.exit("usage: python extract_unity_images.py <game folder> <game id> [viewer dir]")
    root, gid = sys.argv[1], sys.argv[2]
    viewer = sys.argv[3] if len(sys.argv) > 3 else os.path.expanduser("~/pubpets_archive/viewer")
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
    objs = {}
    for p in files:
        try:
            env = UnityPy.load(p)
        except Exception:
            continue
        for o in env.objects:
            if o.type.name != "Texture2D":
                continue
            try:
                n = o.read().m_Name
            except Exception:
                continue
            if NAME.match(n) and n.lower() not in objs:
                objs[n.lower()] = o
    groups = group(objs.keys())
    print("images found:", len(objs))
    gdir = os.path.join(viewer, "games", gid)
    os.makedirs(os.path.join(gdir, "img"), exist_ok=True)
    os.makedirs(os.path.join(gdir, "img", "th"), exist_ok=True)
    total, failed = 0, []
    catalog = []
    for (kind, ep) in sorted(groups, key=lambda x: (x[1], list(KINDS).index(x[0]))):
        items = []
        for num in sorted(groups[(kind, ep)]):
            imgs = []
            for letter, n in sorted(groups[(kind, ep)][num]):
                try:
                    im = objs[n.lower()].read().image
                    fn = n.lower() + ".webp"
                    im.convert("RGBA" if im.mode == "RGBA" and im.getchannel("A").getextrema()[0] < 255 else "RGB") \
                      .save(os.path.join(gdir, "img", fn), "WEBP", quality=88)
                    th = im.convert("RGB")
                    th.thumbnail((480, 480))
                    th.save(os.path.join(gdir, "img", "th", fn), "WEBP", quality=78)
                    total += os.path.getsize(os.path.join(gdir, "img", fn))
                    imgs.append("img/" + fn)
                except Exception as e:
                    failed.append((n, str(e)[:60]))
            if imgs:
                items.append({"id": "%s_ep%02d_%02d" % (kind, ep, num), "title": "%s %d" % (KINDS[kind], num),
                              "thumb": imgs[0].replace("img/", "img/th/"), "images": imgs})
        if items:
            catalog.append({"name": "%s · Ep %d" % (KINDS[kind], ep), "items": items})
    with open(os.path.join(gdir, "images.json"), "w") as fh:
        json.dump({"groups": catalog}, fh, indent=1)
    print("groups:", [(g["name"], len(g["items"])) for g in catalog])
    print("failed:", failed[:6], "| total size: %.0f MB" % (total / 1e6))
    print("wrote", os.path.join(gdir, "images.json"))

if __name__ == "__main__":
    main()
