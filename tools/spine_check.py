# Checks each extracted skeleton: skins, slots, animations, and attachments whose
# image is missing from the atlas (per skin, sequence-aware). For every missing
# image it also looks through the other atlases in the folder, so you can tell a
# wrongly paired atlas from a texture that really is not in the extract.
#   python spine_check.py [games/<id>/cg folder]
import sys, os, json, glob


def parse_atlas(text):
    """-> (set of region names, list of page file names)"""
    ls = text.splitlines()
    regs, pages = set(), []
    for i in range(len(ls) - 1):
        a, b = ls[i].strip(), ls[i + 1].strip()
        if a and ":" not in a and ":" in b:
            if b.startswith("size:"):
                pages.append(a)
            else:
                regs.add(a)
    return regs, pages


def needed(att, name):
    """Atlas region names one attachment needs (Spine 4.x sequences included)."""
    if att.get("type", "region") not in ("region", "mesh", "linkedmesh"):
        return []
    base = att.get("path") or att.get("name") or name
    seq = att.get("sequence")
    if not seq:
        return [base]
    start, digits = seq.get("start", 1), seq.get("digits", 0)
    return [base + str(start + i).zfill(digits) for i in range(seq.get("count", 0))]


cg = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/pubpets_archive/viewer/games/hazelnutlatte/cg")
atlases = {}
for f in glob.glob(os.path.join(cg, "*.atlas")):
    try:
        atlases[os.path.basename(f)[:-6]] = parse_atlas(open(f, encoding="utf-8").read())
    except Exception:
        pass

tot_missing = 0
for f in sorted(glob.glob(os.path.join(cg, "*.json"))):
    sid = os.path.basename(f)[:-5]
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    if not isinstance(d, dict) or "skeleton" not in d:
        continue  # game.json etc.
    rg, pages = atlases.get(sid, (set(), []))
    skins = d.get("skins", [])
    if isinstance(skins, dict):
        skins = [{"name": k, "attachments": v} for k, v in skins.items()]
    info, miss_by_skin, all_miss = [], {}, set()
    for sk in skins:
        n, miss = 0, []
        for slot, atts in sk.get("attachments", {}).items():
            for an, a in atts.items():
                for nm in needed(a, an):
                    n += 1
                    if nm not in rg:
                        miss.append(nm)
        info.append("%s:%d" % (sk.get("name"), n))
        if miss:
            miss_by_skin[sk.get("name")] = miss
            all_miss.update(miss)
    tot_missing += len(all_miss)
    sk = d.get("skeleton", {})
    line = "%-26s slots %-3d bones %-3d anims %-3d skins %s %s" % (
        sid[:26], len(d.get("slots", [])), len(d.get("bones", [])), len(d.get("animations", {})),
        info, "size %dx%d" % (sk.get("width", 0), sk.get("height", 0)))
    if sid not in atlases:
        line += " NO ATLAS FILE"
    print(line)
    no_page = [p for p in pages if not os.path.exists(os.path.join(cg, p))]
    if no_page:
        print("    atlas page file missing:", no_page)
    for sname, miss in miss_by_skin.items():
        print("    skin %-14s MISSING %d e.g. %s" % (sname, len(miss), miss[:3]))
    for nm in sorted(all_miss)[:6]:
        elsewhere = [k for k, (r, _) in atlases.items() if k != sid and nm in r]
        print("      %s -> %s" % (nm, ("found in " + ", ".join(elsewhere[:3])) if elsewhere else "in no atlas"))
print("total attachments with no atlas region:", tot_missing)
