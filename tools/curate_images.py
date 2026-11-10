# Trim and merge the still-image tabs in games/<id>/images.json.
#   python curate_images.py <game id> [viewer dir] [--prune]
# Drops the kinds listed in DROP, merges the kinds listed in MERGE into one tab
# across episodes, and (with --prune) deletes the image files nothing uses.
# Safe to run again: the first run keeps a copy in images.full.json.
import sys, os, json, re, shutil

DROP = ("Backgrounds", "Legacy", "Concept art")
MERGE = ("Pin-ups",)

def kind(name):
    return name.split(" · ")[0]

def curate(groups):
    out, merged = [], {}
    for g in groups:
        k = kind(g["name"])
        if k in DROP:
            continue
        if k in MERGE:
            merged.setdefault(k, {"name": k, "items": []})["items"] += g["items"]
        else:
            out.append(g)
    for k, g in merged.items():
        out.append(g)
        for i, it in enumerate(g["items"], 1):
            it["title"] = "%s %d" % (k[:-1] if k.endswith("s") else k, i)
    return out

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit("usage: python curate_images.py <game id> [viewer dir] [--prune]")
    gid = args[0]
    viewer = args[1] if len(args) > 1 else os.path.expanduser("~/pubpets_archive/viewer")
    gdir = os.path.join(viewer, "games", gid)
    path, full = os.path.join(gdir, "images.json"), os.path.join(gdir, "images.full.json")
    if not os.path.exists(full):
        shutil.copy(path, full)
    groups = curate(json.load(open(full))["groups"])
    json.dump({"groups": groups}, open(path, "w"), indent=1)
    print("tabs now:", [(g["name"], len(g["items"])) for g in groups])
    if "--prune" in sys.argv:
        keep = set()
        for g in groups:
            for it in g["items"]:
                keep.update(it["images"]); keep.add(it["thumb"])
        n = 0
        for sub in ("img", os.path.join("img", "th")):
            d = os.path.join(gdir, sub)
            for f in os.listdir(d) if os.path.isdir(d) else []:
                rel = "/".join(["img"] + (["th"] if sub.endswith("th") else []) + [f])
                if f.endswith(".webp") and rel not in keep:
                    os.remove(os.path.join(d, f)); n += 1
        print("deleted", n, "unused image files")

if __name__ == "__main__":
    main()
