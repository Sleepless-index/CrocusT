# Extract the full-size still images (CGs, backgrounds, scenes) from a Ren'Py game
# as .webp plus small thumbnails, and add the game to the viewer
# (games.json + games/<id>/game.json + games/<id>/images.json).
# Works on the game's .zip or on an already unpacked folder. Reads loose image
# files and .rpa archives (RPA-2.0, RPA-3.0, RPA-3.2). Needs: pip install Pillow
#   python extract_renpy.py <game .zip or folder> <game id> "<Game title>" [viewer dir] [options]
# Options:
#   --min-w N   skip images narrower than N px (default 1000, drops sprites and UI)
#   --min-h N   skip images shorter than N px (default 560)
#   --all       keep every image, no size filter and no gui/ui folder filter
#   --keep      keep the temporary folder the zip was unpacked into
# Example:
#   python extract_renpy.py /storage/emulated/0/Download/NewStart-0.zip newstart "New Start" viewer
import sys, os, re, io, json, zlib, pickle, shutil, hashlib, zipfile, tempfile, collections

IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")
SKIP_DIRS = {"gui", "fonts", "font", "screens", "icons", "icon", "ui", "buttons", "button",
             "renpy", "lib", "common", "saves", "tl"}


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "x"


def natkey(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s.lower())]


class SafeUnpickler(pickle.Unpickler):
    # The RPA index only holds dicts, lists, tuples, ints and strings. Ren'Py 8 stores
    # byte prefixes through _codecs.encode, so that one call is allowed and nothing else.
    def find_class(self, module, name):
        if (module, name) == ("_codecs", "encode"):
            import codecs
            return codecs.encode
        raise pickle.UnpicklingError("unexpected object in archive index: %s.%s" % (module, name))


def read_rpa_index(fh):
    fh.seek(0)
    head = fh.readline().decode("latin1", "replace").split()
    if not head or not head[0].startswith("RPA-"):
        return None, 0
    ver = head[0]
    offset = int(head[1], 16)
    key = 0
    if ver == "RPA-3.0":
        key = int(head[2], 16)
    elif ver == "RPA-3.2":
        for part in head[3:]:
            key ^= int(part, 16)
    elif ver != "RPA-2.0":
        return None, 0
    fh.seek(offset)
    index = SafeUnpickler(io.BytesIO(zlib.decompress(fh.read())), encoding="latin1").load()
    out = {}
    for name, parts in index.items():
        if not parts:
            continue
        p = parts[0]
        off, length = p[0] ^ key, p[1] ^ key
        prefix = p[2] if len(p) > 2 else b""
        if isinstance(prefix, str):
            prefix = prefix.encode("latin1")
        out[name] = (off, length, prefix)
    return out, key


def clean_parts(rel):
    return [p for p in rel.replace("\\", "/").split("/") if p]


def wanted(rel, allfiles):
    parts = clean_parts(rel)
    if not parts or not parts[-1].lower().endswith(IMG_EXT):
        return False
    if allfiles:
        return True
    return not any(p.lower() in SKIP_DIRS for p in parts[:-1])


def collect(root, allfiles):
    """-> list of (relpath inside game, loader()) for every candidate image."""
    found = []
    for r, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d.lower() not in ("renpy", "lib", "__macosx")]
        # a path relative to the nearest "game" folder, so images/cg/a.png stays images/cg/a.png
        parts = clean_parts(os.path.relpath(r, root))
        base = parts[parts.index("game") + 1:] if "game" in parts else parts
        for f in files:
            full = os.path.join(r, f)
            low = f.lower()
            if low.endswith(".rpa"):
                try:
                    fh = open(full, "rb")
                    idx, _ = read_rpa_index(fh)
                except Exception as e:
                    print("could not read", full, "-", e)
                    continue
                if idx is None:
                    print("not a supported RPA:", full)
                    continue
                n = 0
                for name, (off, length, prefix) in idx.items():
                    if wanted(name, allfiles):
                        found.append(("/".join(clean_parts(name)), (lambda fh=fh, o=off, l=length, p=prefix:
                                                                       (fh.seek(o), p + fh.read(l - len(p)))[1])))
                        n += 1
                print("%s: %d files in index, %d images" % (f, len(idx), n))
            elif low.endswith(IMG_EXT):
                rel = "/".join(base + [f])
                if wanted(rel, allfiles):
                    found.append((rel, lambda p=full: open(p, "rb").read()))
    return found


def pretty(s):
    return re.sub(r"\s+", " ", re.sub(r"[_\-]+", " ", s)).strip()


def main():
    args = [a for a in sys.argv[1:]]
    opts = {"--min-w": 1000, "--min-h": 560}
    allfiles = keep = False
    pos = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in opts:
            opts[a] = int(args[i + 1]); i += 2; continue
        if a == "--all":
            allfiles = True
        elif a == "--keep":
            keep = True
        else:
            pos.append(a)
        i += 1
    if len(pos) < 3:
        sys.exit('usage: python extract_renpy.py <game .zip or folder> <id> "<title>" [viewer dir] '
                 "[--min-w N] [--min-h N] [--all] [--keep]")
    src, gid, title = pos[0], pos[1], pos[2]
    viewer = pos[3] if len(pos) > 3 else os.path.expanduser("~/pubpets_archive/viewer")
    try:
        from PIL import Image
    except ImportError:
        sys.exit("Pillow is missing: pkg install python-pillow")

    tmp = None
    root = src
    if os.path.isfile(src) and src.lower().endswith(".zip"):
        tmp = tempfile.mkdtemp(prefix="renpy_", dir=os.path.dirname(os.path.abspath(viewer)))
        print("unpacking images and archives to", tmp)
        with zipfile.ZipFile(src) as z:
            for m in z.infolist():
                low = m.filename.lower()
                parts = [p.lower() for p in clean_parts(m.filename)]
                if m.is_dir() or "renpy" in parts or "lib" in parts or "__macosx" in parts:
                    continue
                if low.endswith(".rpa") or low.endswith(IMG_EXT):
                    z.extract(m, tmp)
        root = tmp
    elif not os.path.isdir(src):
        sys.exit("Not a folder or .zip: " + src)

    try:
        cands = collect(root, allfiles)
        print("candidate images:", len(cands))
        gdir = os.path.join(viewer, "games", gid)
        imgdir, thdir = os.path.join(gdir, "img"), os.path.join(gdir, "img", "th")
        os.makedirs(thdir, exist_ok=True)

        seen, kept, small, bad, total = set(), [], 0, [], 0
        for rel, load in sorted(cands, key=lambda c: natkey(c[0])):
            try:
                data = load()
                h = hashlib.md5(data).hexdigest()
                if h in seen:
                    continue
                seen.add(h)
                im = Image.open(io.BytesIO(data))
                im.load()
            except Exception as e:
                bad.append((rel, str(e)[:50]))
                continue
            if not allfiles and (im.width < opts["--min-w"] or im.height < opts["--min-h"]):
                small += 1
                continue
            parts = clean_parts(rel)
            if parts and parts[0].lower() == "images":
                parts = parts[1:]
            stem = os.path.splitext(parts[-1])[0]
            fn = slug("_".join(parts[:-1] + [stem])) + ".webp"
            if os.path.exists(os.path.join(imgdir, fn)):
                fn = slug("_".join(parts[:-1] + [stem])) + "_" + h[:6] + ".webp"
            alpha = im.mode in ("RGBA", "LA", "P") and im.convert("RGBA").getchannel("A").getextrema()[0] < 255
            out = im.convert("RGBA" if alpha else "RGB")
            out.save(os.path.join(imgdir, fn), "WEBP", quality=88)
            th = im.convert("RGB")
            th.thumbnail((480, 480))
            th.save(os.path.join(thdir, fn), "WEBP", quality=78)
            total += os.path.getsize(os.path.join(imgdir, fn))
            kept.append((parts[:-1], stem, fn))

        print("kept: %d | skipped as too small: %d | unreadable: %d | size: %.0f MB"
              % (len(kept), small, len(bad), total / 1e6))
        if bad:
            print("unreadable:", bad[:5])
        if not kept:
            print("Nothing kept. Try --all, or lower --min-w / --min-h.")
            return

        # tabs: one per folder; if that gives too many tabs, one per top-level folder
        def gname(dirs, depth):
            d = dirs[:depth] if depth else dirs
            return " \u00b7 ".join(pretty(x).title() for x in d) or "Images"
        names = {gname(k[0], 0) for k in kept}
        depth = 0 if len(names) <= 20 else 1
        groups = collections.OrderedDict()
        for dirs, stem, fn in kept:
            groups.setdefault(gname(dirs, depth), []).append((stem, fn))

        catalog = []
        for gn in sorted(groups, key=natkey):
            # a, b, c... after a number are variants of one image (cg03a, cg03b)
            bucket = collections.OrderedDict()
            for stem, fn in sorted(groups[gn], key=lambda x: natkey(x[0])):
                m = re.match(r"^(.*\d)([a-z])$", stem, re.I)
                bucket.setdefault(m.group(1) if m else stem, []).append((stem, fn))
            items = []
            for base, vs in bucket.items():
                if len(vs) == 1 and vs[0][0] != base:
                    base = vs[0][0]
                items.append({"id": slug(gn + "_" + base), "title": pretty(base),
                              "thumb": "img/th/" + vs[0][1], "images": ["img/" + v[1] for v in vs]})
            catalog.append({"name": gn, "items": items})

        with open(os.path.join(gdir, "images.json"), "w") as fh:
            json.dump({"groups": catalog}, fh, indent=1)
        with open(os.path.join(gdir, "game.json"), "w") as fh:
            json.dump({"title": title, "groups": []}, fh, indent=1)
        gp = os.path.join(viewer, "games.json")
        games = json.load(open(gp)) if os.path.exists(gp) else []
        games = [g for g in games if g.get("id") != gid]
        games.append({"id": gid, "title": title, "path": "games/" + gid, "runtime": "spine-webgl.js",
                      "cover": "games/%s/img/th/%s" % (gid, kept[0][2])})
        with open(gp, "w") as fh:
            json.dump(games, fh, indent=1)
        print("groups:", [(g["name"], len(g["items"])) for g in catalog])
        print("wrote", os.path.join(gdir, "images.json"), "and updated games.json")
    finally:
        if tmp and not keep:
            shutil.rmtree(tmp, ignore_errors=True)
        elif tmp:
            print("kept unpacked files in", tmp)


if __name__ == "__main__":
    main()
