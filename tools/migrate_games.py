# One-time move of the PubPets files into games/pubpets/ and creation of
# games.json + games/pubpets/game.json, so the viewer can offer a game picker.
#   python migrate_games.py [path/to/viewer]
import os, sys, json, shutil

base = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/pubpets_archive/viewer")
gdir = os.path.join(base, "games", "pubpets")
os.makedirs(gdir, exist_ok=True)
for d in ("cg", "thumbs", "audio"):
    src, dst = os.path.join(base, d), os.path.join(gdir, d)
    if os.path.isdir(src) and not os.path.exists(dst):
        shutil.move(src, dst)
        print("moved", d)

girls = [
    ("Hetty", lambda i: "hedi%d" % i),
    ("Alice", lambda i: "ALS-8" if i == 8 else "ailisi%d" % i),
    ("Anto", lambda i: "Anto_CG_%02d" % i if i <= 3 else "antuo%d" % i),
]
groups, cover = [], ""
for girl, fn in girls:
    items = []
    for i in range(1, 11):
        cid = fn(i)
        if not os.path.exists(os.path.join(gdir, "cg", cid + ".json")):
            continue
        item = {"id": cid, "title": "%s %d" % (girl, i)}
        th = "thumbs/Thumbnail_%s_CG_%02d.png" % (girl, i)
        if os.path.exists(os.path.join(gdir, th)):
            item["thumb"] = th
            cover = cover or "games/pubpets/" + th
        items.append(item)
    groups.append({"name": girl, "items": items})
with open(os.path.join(gdir, "game.json"), "w") as fh:
    json.dump({"title": "PubPets", "groups": groups}, fh, indent=1)

gp = os.path.join(base, "games.json")
games = json.load(open(gp)) if os.path.exists(gp) else []
games = [g for g in games if g.get("id") != "pubpets"]
games.append({"id": "pubpets", "title": "PubPets", "path": "games/pubpets",
              "runtime": "spine-webgl.js", "cover": cover})
with open(gp, "w") as fh:
    json.dump(games, fh, indent=1)
print("CGs listed:", sum(len(g["items"]) for g in groups), "| games.json has", len(games), "game(s)")
