# Extract the pictures (CGs, backgrounds, titles, enemies) from an RPG Maker MV/MZ game
# as .webp plus thumbnails and add the game to the viewer (games.json +
# games/<id>/game.json + games/<id>/images.json). Handles plain .png and encrypted
# .rpgmvp / .png_ files (key read from data/System.json, with a PNG-header fallback).
# Needs: pip install Pillow     Tabs = one per img/ subfolder.
#   python extract_rpgmaker.py <unpacked game folder> <game id> "<Game title>" [viewer dir] [options]
# Options:
#   --folders A,B   img/ subfolders to read (default pictures,parallaxes,titles1,titles2,
#                   battlebacks1,battlebacks2,enemies). Add characters,faces,... if you want them
#   --min-w N       skip images narrower than N px (default 200)
#   --min-h N       skip images shorter than N px (default 150)
#   --skip REGEX    drop files whose name matches (case-insensitive)
#   --split         split the big pictures folder into tabs: by subfolder if it has any, else
#                   by the first word of the file name (tabs under 6 images go to "Other")
#   --scenes        tabs by the scene number in names like T4-C0-F0010-00 (T4 = scene 4); names
#                   without one go by their first letter, number-only names to "Misc"
#   --scene-digits N  with --scenes, keep only the first N digits (T51, T52 -> T5). Default: all
#   --tabs A,B,C    like --split but only the names listed get a tab (first match wins),
#                   the rest go to "Other". Matches CamelCase words: Au matches CasaAuExt, not Aurora
#   --list          only print what would be made, write nothing
# Example:
#   python extract_rpgmaker.py ~/neet neet "How to Raise a Happy NEET" viewer --list
import sys, os, re, io, json, hashlib, collections

DEFAULT_FOLDERS = "pictures,parallaxes,titles1,titles2,battlebacks1,battlebacks2,enemies"
EXTS = (".png", ".rpgmvp", ".png_", ".jpg", ".jpeg", ".webp")
PNG_HEAD = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 0x0D, 0x49, 0x48, 0x44, 0x52])


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "x"


def natkey(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s.lower())]


def pretty(s):
    return re.sub(r"\s+", " ", re.sub(r"[_\-]+", " ", s)).strip()


def variant_base(stem):
    """cg03a -> cg03, CG_01_2 -> CG_01. Anything else stays on its own (Scene1, Scene2 are different images)."""
    m = re.match(r"^(.*\d)[_\-\s]?[a-z]$", stem, re.I) or re.match(r"^(.*\d)[_\-\s]\d{1,2}$", stem)
    return m.group(1) if m else stem


def tab_of(name):
    """first word of the name with digits stripped: Dia13_Alexa_P -> Dia"""
    w = re.split(r"[_\-\s.]+", name.strip())[0]
    w = re.sub(r"\d+$", "", w) or w
    return w[:1].upper() + w[1:]


def scene_of(name, digits):
    m = re.search(r"(?:^|[-_])T(\d+)(?=[-_])", name)
    if m:
        return "T" + (m.group(1)[:digits] if digits else m.group(1))
    w = re.match(r"[A-Za-z]+", name)
    return w.group(0)[:1].upper() if w else "Misc"


def tab_from_list(name, wanted):
    for w in wanted:
        if re.search(r"(?:^|[^A-Za-z]|(?<=[a-z]))" + re.escape(w) + r"(?![a-z])", name):
            return w
    return "Other"


def find_root(path):
    for r, dirs, files in os.walk(path):
        if os.path.isdir(os.path.join(r, "img")) and os.path.isfile(os.path.join(r, "data", "System.json")):
            return r
    sys.exit("No RPG Maker project (img/ + data/System.json) found under " + path)


def read_key(root):
    try:
        with open(os.path.join(root, "data", "System.json"), encoding="utf-8-sig") as fh:
            k = json.load(fh).get("encryptionKey")
        if k:
            return bytes(int(k[i:i + 2], 16) for i in range(0, len(k), 2))
    except Exception:
        pass
    return None


def decode(raw, name, key):
    low = name.lower()
    if low.endswith((".rpgmvp", ".png_")):
        body = bytearray(raw[16:])
        head = bytes(a ^ b for a, b in zip(body[:16], key)) if key else PNG_HEAD
        return head + bytes(body[16:])
    return raw


def main():
    split = scenes = False
    args, pos, opts, only_list = sys.argv[1:], [], {"--folders": DEFAULT_FOLDERS, "--min-w": 200, "--min-h": 150, "--skip": None, "--tabs": None, "--scene-digits": 0}, False
    i = 0
    while i < len(args):
        a = args[i]
        if a in opts:
            opts[a] = int(args[i + 1]) if a.startswith("--min") or a == "--scene-digits" else args[i + 1]; i += 2; continue
        if a == "--list":
            only_list = True
        elif a == "--split":
            split = True
        elif a == "--scenes":
            scenes = True
        else:
            pos.append(a)
        i += 1
    if len(pos) < 3:
        sys.exit('usage: python extract_rpgmaker.py <game folder> <id> "<title>" [viewer dir] '
                 "[--folders A,B] [--min-w N] [--min-h N] [--skip RE] [--split] [--scenes] [--scene-digits N] [--tabs A,B] [--list]")
    src, gid, title = pos[:3]
    viewer = pos[3] if len(pos) > 3 else os.path.expanduser("~/pubpets_archive/viewer")
    try:
        from PIL import Image
    except ImportError:
        sys.exit("Pillow is missing: pkg install python-pillow")
    root = find_root(src)
    key = read_key(root)
    print("project:", root, "| encryption key:", "yes" if key else "none")
    skip = re.compile(opts["--skip"], re.I) if opts["--skip"] else None

    folders = [f.strip() for f in opts["--folders"].split(",") if f.strip()]
    # tab -> stem -> [(sortname, loader)]
    tabs = collections.OrderedDict()
    seen, small, bad, total, nfiles = set(), 0, [], 0, 0
    kept = []   # (tab, stem, outname, data)
    for f in folders:
        base = os.path.join(root, "img", f)
        if not os.path.isdir(base):
            print("no img/%s folder, skipped" % f)
            continue
        for r, _, files in os.walk(base):
            for fn in sorted(files, key=natkey):
                if not fn.lower().endswith(EXTS) or (skip and skip.search(fn)):
                    continue
                nfiles += 1
                rel = os.path.relpath(os.path.join(r, fn), base)
                stem = os.path.splitext(rel)[0].replace(os.sep, "/")
                try:
                    data = decode(open(os.path.join(r, fn), "rb").read(), fn, key)
                    h = hashlib.md5(data).hexdigest()
                    if h in seen:
                        continue
                    seen.add(h)
                    im = Image.open(io.BytesIO(data))
                    w, hh = im.size
                except Exception as e:
                    bad.append((f + "/" + rel, str(e)[:40]))
                    continue
                if w < opts["--min-w"] or hh < opts["--min-h"]:
                    small += 1
                    continue
                kept.append((f, stem, data))
    print("files seen: %d | kept: %d | too small: %d | unreadable: %d %s" % (nfiles, len(kept), small, len(bad), bad[:5]))
    if not kept:
        print("Nothing kept. Check the key/encryption, or lower --min-w / --min-h.")
        return

    wanted = [t.strip() for t in opts["--tabs"].split(",") if t.strip()] if opts["--tabs"] else None
    names, tabmap = set(), collections.OrderedDict()
    for f, stem, data in kept:
        fn = slug(f + "_" + stem) + ".webp"
        if fn in names:
            fn = slug(f + "_" + stem) + "_" + hashlib.md5(data).hexdigest()[:6] + ".webp"
        names.add(fn)
        tab = pretty(f).title()
        if f == "pictures" and (split or scenes or wanted):
            if "/" in stem:
                tab = pretty(stem.split("/")[0]).title()
            elif wanted:
                tab = tab_from_list(stem, wanted)
            elif scenes:
                tab = scene_of(stem, opts["--scene-digits"])
            else:
                tab = tab_of(stem)
        tabmap.setdefault(tab, collections.OrderedDict()).setdefault(variant_base(stem), []).append((stem, fn, data))
    if (split or scenes) and not wanted:
        for t in [t for t, b in tabmap.items() if sum(len(v) for v in b.values()) < 6 and t != "Other"]:
            if t in ("Titles1", "Titles2"):
                continue
            other = tabmap.setdefault("Other", collections.OrderedDict())
            for b, v in tabmap.pop(t).items():
                other.setdefault(b, []).extend(v)
    catalog = []
    for tab in sorted(tabmap, key=lambda t: (t == "Other", natkey(t))):
        bases = tabmap[tab]
        items = []
        for b in sorted(bases, key=natkey):
            vs = sorted(bases[b], key=lambda x: natkey(x[0]))
            it = {"id": slug(tab + "_" + b), "title": pretty(b.split("/")[-1]),
                  "thumb": "img/th/" + vs[0][1], "images": ["img/" + v[1] for v in vs]}
            # frames numbered -00, -01 ... of one picture: the viewer offers a play button
            if len(vs) > 1 and all(re.search(r"[_\-\s]\d{1,2}$", v[0]) for v in vs):
                it["anim"] = True
            items.append(it)
        catalog.append({"name": tab, "items": items})
    print("tabs:", [(g["name"], len(g["items"]), sum(len(i["images"]) for i in g["items"])) for g in catalog])
    if only_list:
        print("(nothing written)")
        return

    gdir = os.path.join(viewer, "games", gid)
    imgdir, thdir = os.path.join(gdir, "img"), os.path.join(gdir, "img", "th")
    os.makedirs(thdir, exist_ok=True)
    done, failed = 0, []
    for bases in tabmap.values():
        for vs in bases.values():
            for stem, fn, data in vs:
                try:
                    im = Image.open(io.BytesIO(data))
                    alpha = im.mode in ("RGBA", "LA", "P") and im.convert("RGBA").getchannel("A").getextrema()[0] < 255
                    im.convert("RGBA" if alpha else "RGB").save(os.path.join(imgdir, fn), "WEBP", quality=88)
                    th = im.convert("RGBA" if alpha else "RGB")   # keep transparency: layers are overlays
                    th.thumbnail((480, 480))
                    th.save(os.path.join(thdir, fn), "WEBP", quality=78)
                    total += os.path.getsize(os.path.join(imgdir, fn))
                except Exception as e:
                    failed.append((fn, str(e)[:40]))
                done += 1
                if done % 100 == 0:
                    print("  %d / %d" % (done, len(kept)))
    print("written: %d | failed: %d %s | total size: %.0f MB" % (done - len(failed), len(failed), failed[:5], total / 1e6))

    with open(os.path.join(gdir, "images.json"), "w") as fh:
        json.dump({"groups": catalog}, fh, indent=1)
    with open(os.path.join(gdir, "game.json"), "w") as fh:
        json.dump({"title": title, "groups": []}, fh, indent=1)
    gp = os.path.join(viewer, "games.json")
    games = json.load(open(gp)) if os.path.exists(gp) else []
    games = [g for g in games if g.get("id") != gid]
    games.append({"id": gid, "title": title, "path": "games/" + gid, "runtime": "spine-webgl.js",
                  "cover": "games/%s/%s" % (gid, catalog[0]["items"][0]["thumb"])})
    with open(gp, "w") as fh:
        json.dump(games, fh, indent=1)
    print("wrote", os.path.join(gdir, "images.json"), "and updated games.json")


if __name__ == "__main__":
    main()
