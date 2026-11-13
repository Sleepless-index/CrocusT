# Rebuild an RPG Maker MV game's picture scenes for the viewer: pictures that the game shows
# together (stacked by picture slot, higher slot = on top), the PictureAnimation plugin's frame
# animation (cells, speed, loop type), picture moves, and the pictures that act as buttons
# (PictureCallCommon: P_CALL_CE / P_CALL_SWITCH). Game conditions are NOT evaluated: every branch
# of an event becomes its own scene. Writes games/<id>/scenes.json, pic/ and scene/ (thumbnails).
# Needs: pip install Pillow
#   python rpgm_scenes.py <unpacked game folder> <game id> [viewer dir] [options]
# Options:
#   --list        only print what would be made, write nothing
#   --no-thumbs   skip scene thumbnails (faster)
#   --max N       at most N scenes per event list (default 6)
#   --group MODE  tabs by the event's name prefix (default, "name": 乳首（おさわり -> 乳首) or by
#                 where it lives ("source": Common events / Map001). Small groups go to "Other"
import sys, os, re, io, json, copy, hashlib, collections

PLUGIN_CMDS = {"PA_INIT": "INIT", "ピクチャのアニメーション準備": "INIT",
               "PA_START": "START", "ピクチャのアニメーション開始": "START",
               "PA_START_LOOP": "LOOP", "ピクチャのループアニメーション開始": "LOOP",
               "PA_STOP": "STOP", "PA_STOP_FORCE": "STOP", "ピクチャのアニメーション終了": "STOP",
               "ピクチャのアニメーション強制終了": "STOP",
               "PA_SET_CELL": "CELL", "ピクチャのセル設定": "CELL",
               "P_CALL_CE": "CE", "P_CALL_SWITCH": "SW", "P_CALL_CE_REMOVE": "RM", "P_CALL_SWITCH_REMOVE": "RM"}
LAYOUTS = {"連番": "seq", "縦": "v", "横": "h"}
EXTS = (".png", ".rpgmvp", ".png_", ".jpg", ".jpeg", ".webp")
PNG_HEAD = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 0x0D, 0x49, 0x48, 0x44, 0x52])
MAX_STATES, MAX_RAW_SNAPS = 24, 40


# English labels for the game's Japanese event-name prefixes. Anything not listed becomes "Group N".
EN = {"水着": "Swimsuit", "隠しボタン": "Hidden button", "隠しボ": "Hidden button", "解放系使用": "Unlock use",
      "解放系説明": "Unlock info", "吐息": "Breathing", "おさわりカットイン": "Touch cut-in", "カットイン": "Cut-in",
      "外出し": "Pull-out", "外出しアニメ": "Pull-out animation", "サブシナリオ": "Sub scenario",
      "メインシナリオ": "Main scenario", "シナリオラスト": "Final scenario", "パンツ": "Panties",
      "ベースの裸": "Base nude", "ずらした服": "Shifted clothes", "ずれ水まんピス": "Shifted swimsuit thrust",
      "通常水まんピス": "Swimsuit thrust", "通常水あなピス": "Swimsuit thrust (rear)", "まんこピストン": "Thrust",
      "アナルピストン": "Thrust (rear)", "トイレ": "Toilet", "トイレアップデート": "Toilet update",
      "結婚、妊娠、海": "Marriage / pregnancy / sea", "座るニート": "Sitting NEET", "地面のローター": "Floor toy",
      "少し感じる表情": "Light expression", "商品説明": "Item info", "散歩": "Walk"}


def label(g):
    return EN.get(g, g)


def has_jp(t):
    return any(ord(c) > 0x2E80 for c in t)


def name_group(name):
    g = re.split(r"[（(\s\u3000_\-]", name.strip())[0].rstrip("0123456789") if name else ""
    return g if g and not re.match(r"^(EV|ev)$", g) else "Other"


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "x"


def jload(p):
    with open(p, encoding="utf-8-sig") as fh:
        return json.load(fh)


def find_root(path):
    for r, dirs, files in os.walk(path):
        if os.path.isdir(os.path.join(r, "img")) and os.path.isfile(os.path.join(r, "data", "System.json")):
            return r
    sys.exit("No RPG Maker project (img/ + data/System.json) under " + path)


def read_key(root):
    try:
        k = jload(os.path.join(root, "data", "System.json")).get("encryptionKey")
        if k:
            return bytes(int(k[i:i + 2], 16) for i in range(0, len(k), 2))
    except Exception:
        pass
    return None


def screen_size(root):
    """-> (w, h, where it came from). Plugin parameters (Community_Basic...) win, then System.json."""
    try:
        txt = open(os.path.join(root, "js", "plugins.js"), encoding="utf-8-sig").read()
        for pl in json.loads(txt[txt.index("["): txt.rindex("]") + 1]):
            if not pl.get("status"):
                continue
            pr = pl.get("parameters") or {}
            def pick(rx):
                for k, v in pr.items():
                    if re.fullmatch(rx, k, re.I) and str(v).strip().isdigit() and int(v) > 0:
                        return int(v)
            w, h = pick(r"screen\s*width"), pick(r"screen\s*height")
            if w and h:
                return w, h, "plugin " + pl.get("name", "?")
    except Exception:
        pass
    try:
        adv = jload(os.path.join(root, "data", "System.json")).get("advanced") or {}
        if adv.get("screenWidth"):
            return int(adv["screenWidth"]), int(adv["screenHeight"]), "System.json"
    except Exception:
        pass
    return 816, 624, "default"


def decode(raw, name, key):
    if name.lower().endswith((".rpgmvp", ".png_")):
        body = bytearray(raw[16:])
        head = bytes(a ^ b for a, b in zip(body[:16], key)) if key else PNG_HEAD
        return head + bytes(body[16:])
    return raw


# ---------------------------------------------------------------- event lists
def event_lists(root):
    """[{label, kind, cid, switches, cmds}]"""
    d = os.path.join(root, "data")
    out = []
    p = os.path.join(d, "CommonEvents.json")
    if os.path.exists(p):
        for e in jload(p):
            if e:
                sw = [e["switchId"]] if e.get("trigger") in (1, 2) and e.get("switchId") else []
                out.append({"label": "Common %s %s" % (e["id"], e.get("name", "")), "kind": "common", "cid": e["id"],
                            "switches": sw, "cmds": e.get("list") or [], "group": "Common events",
                            "gname": name_group(e.get("name", ""))})
    names = {}
    try:
        for m in jload(os.path.join(d, "MapInfos.json")):
            if m:
                names[m["id"]] = m.get("name", "")
    except Exception:
        pass
    for f in sorted(os.listdir(d)):
        m = re.match(r"Map(\d+)\.json$", f)
        if not m:
            continue
        mid = int(m.group(1))
        try:
            mp = jload(os.path.join(d, f))
        except Exception:
            continue
        for e in mp.get("events") or []:
            if not e:
                continue
            for i, pg in enumerate(e.get("pages") or []):
                c = pg.get("conditions") or {}
                sw = [c[k + "Id"] for k in ("switch1", "switch2") if c.get(k + "Valid") and c.get(k + "Id")]
                out.append({"label": "Map%03d ev%s %s p%d" % (mid, e["id"], e.get("name", ""), i + 1), "kind": "map",
                            "cid": None, "switches": sw, "cmds": pg.get("list") or [],
                            "group": "Map%03d %s" % (mid, names.get(mid, "")) if names.get(mid) else "Map%03d" % mid,
                            "gname": name_group(e.get("name", ""))})
    return out


def build_nodes(lst):
    n = len(lst)

    def block(i, indent):
        nodes = []
        while i < n:
            c = lst[i]
            code, ind = c["code"], c.get("indent", 0)
            if ind < indent:
                break
            if code == 0:
                i += 1
            elif code == 111:
                then, i = block(i + 1, ind + 1)
                els = []
                if i < n and lst[i]["code"] == 411 and lst[i].get("indent", 0) == ind:
                    els, i = block(i + 1, ind + 1)
                if i < n and lst[i]["code"] == 412 and lst[i].get("indent", 0) == ind:
                    i += 1
                nodes.append(("if", [then, els]))
            elif code == 102:
                i += 1
                brs = []
                while i < n and lst[i].get("indent", 0) == ind and lst[i]["code"] in (402, 403):
                    body, i = block(i + 1, ind + 1)
                    brs.append(body)
                if i < n and lst[i]["code"] == 404 and lst[i].get("indent", 0) == ind:
                    i += 1
                if brs:
                    nodes.append(("if", brs))
            elif code == 112:
                body, i = block(i + 1, ind + 1)
                if i < n and lst[i]["code"] == 413 and lst[i].get("indent", 0) == ind:
                    i += 1
                nodes.append(("seq", body))
            else:
                nodes.append(("cmd", c))
                i += 1
        return nodes, i
    return block(0, 0)[0]


# ---------------------------------------------------------------- simulation
def num(v):
    try:
        return int(str(v).strip())
    except Exception:
        return None


def split_args(s):
    out, depth, cur, q = [], 0, "", None
    for ch in s:
        if q:
            cur += ch
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch; cur += ch
        elif ch in "([{":
            depth += 1; cur += ch
        elif ch in ")]}":
            depth -= 1; cur += ch
        elif ch == "," and depth == 0:
            out.append(cur.strip()); cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


class Sim:
    """Walks an event list and records every picture it shows as a layer with a start time `d` and
    an end time `e` (in game frames, 60 per second). Waits advance the clock, so a sequence of
    'show, wait, show' becomes one timeline scene instead of several pieces."""

    def __init__(self, stats):
        self.calls = set()
        self.stats = stats

    def new_state(self):
        return {"slots": {}, "pa": None, "binds": {}, "t": 0, "log": []}

    def show(self, st, slot, name, origin, x, y, sx, sy, op, bl):
        if slot is None or not name:
            return
        L = {"s": slot, "n": name, "o": origin or 0, "x": x or 0, "y": y or 0, "sx": 100 if sx is None else sx,
             "sy": 100 if sy is None else sy, "op": 255 if op is None else op, "bl": bl or 0, "m": [],
             "d": st["t"], "e": None}
        if st["pa"]:
            L["a"] = dict(st["pa"]); st["pa"] = None
        if slot in st["binds"]:
            L["b"] = dict(st["binds"][slot]); self.stats["bound"] += 1
        old = st["slots"].get(slot)
        if old is not None and old["e"] is None:
            old["e"] = st["t"]                      # a new picture in the same slot replaces the old one
        st["slots"][slot] = L
        st["log"].append(L)

    def erase(self, st, slot):
        L = st["slots"].pop(slot, None)
        if L is not None and L["e"] is None:
            L["e"] = st["t"]

    def script(self, st, text):
        for m in re.finditer(r"\$gameScreen\.showPicture\((.*)\)\s*;?", text):
            a = split_args(m.group(1))
            if len(a) >= 2 and a[1][:1] in "\"'" and a[1][-1:] == a[1][:1]:
                g = lambda k: num(a[k]) if len(a) > k else None
                # script form: showPicture(id, name, origin, x, y, scaleX, scaleY, opacity, blend)
                self.show(st, num(a[0]), a[1][1:-1], g(2), g(3), g(4), g(5), g(6), g(7), g(8))
        for m in re.finditer(r"\$gameScreen\.erasePicture\(\s*(\d+)\s*\)", text):
            self.erase(st, int(m.group(1)))
        for m in re.finditer(r"\$gameScreen\.picture\(\s*(\d+)\s*\)\.(_x|_y|_scaleX|_scaleY|_opacity)\s*=\s*(-?\d+)\s*;", text):
            L = st["slots"].get(int(m.group(1)))
            if L:
                L[{"_x": "x", "_y": "y", "_scaleX": "sx", "_scaleY": "sy", "_opacity": "op"}[m.group(2)]] = int(m.group(3))

    def plugin(self, st, text):
        t = text.replace("\u3000", " ").split()
        if not t:
            return
        kind = PLUGIN_CMDS.get(t[0].upper() if t[0].isascii() else t[0])
        a = t[1:]
        if kind == "INIT" and len(a) >= 2 and num(a[0]) and num(a[1]):
            st["pa"] = {"n": num(a[0]), "i": max(1, num(a[1])), "lay": LAYOUTS.get(a[2], "seq") if len(a) > 2 else "seq",
                        "f": num(a[3]) or 0 if len(a) > 3 else 0}
        elif kind in ("START", "LOOP") and a and num(a[0]) is not None:
            L = st["slots"].get(num(a[0]))
            if L and L.get("a"):
                L["a"]["go"] = 1
                L["a"]["t"] = num(a[1]) or 1 if len(a) > 1 else 1
                L["a"]["loop"] = 1 if kind == "LOOP" else 0
                if len(a) > 2:
                    try:
                        L["a"]["p"] = [int(v) for v in json.loads("".join(a[2:]))]
                    except Exception:
                        pass
        elif kind == "CELL" and len(a) >= 2 and num(a[0]) is not None and num(a[1]):
            L = st["slots"].get(num(a[0]))
            if L and L.get("a"):
                L["a"]["cell"] = num(a[1])
        elif kind in ("CE", "SW") and len(a) >= 2 and num(a[0]) is not None and num(a[1]) is not None:
            b = {"k": "ce" if kind == "CE" else "sw", "id": num(a[1])}
            st["binds"][num(a[0])] = b
            self.stats["bindcmd"] += 1
            L = st["slots"].get(num(a[0]))
            if L:
                L["b"] = dict(b); self.stats["bound"] += 1
        elif kind == "RM" and a and num(a[0]) is not None:
            st["binds"].pop(num(a[0]), None)
            L = st["slots"].get(num(a[0]))
            if L:
                L.pop("b", None)

    def apply(self, st, c):
        code, p = c["code"], c["parameters"]
        try:
            if code == 231:
                self.show(st, p[0], p[1], p[2], p[4] if p[3] == 0 else 0, p[5] if p[3] == 0 else 0, p[6], p[7], p[8], p[9])
            elif code in (355, 655):
                self.script(st, str(p[0]))
            elif code == 232:
                L = st["slots"].get(p[0])
                if L and len(L["m"]) < 4:
                    d = max(int(p[10]), 0)
                    L["m"].append({"at": st["t"] - L["d"], "d": d, "x": p[4] if p[3] == 0 else None,
                                   "y": p[5] if p[3] == 0 else None, "sx": p[6], "sy": p[7], "op": p[8]})
                    if len(p) > 11 and p[11]:
                        st["t"] += d                  # "wait for completion"
            elif code == 235:
                self.erase(st, p[0])
            elif code == 230:
                st["t"] += max(int(p[0]), 0)
            elif code == 356:
                self.plugin(st, str(p[0]))
            elif code == 117:
                self.calls.add(p[0])
        except (IndexError, TypeError, KeyError, ValueError):
            pass

    def run(self, nodes, states):
        for kind, body in nodes:
            if kind == "cmd":
                for st in states:
                    self.apply(st, body)
            elif kind == "seq":
                states = self.run(body, states)
            else:
                out = []
                for br in body:
                    out += self.run(br, [copy.deepcopy(s) for s in states])
                seen, states = set(), []
                for s in out:
                    sig = (tuple((l["s"], l["n"], l["x"], l["y"], l["d"], l["e"]) for l in s["log"]),
                           tuple(sorted(s["slots"])), tuple(sorted(s["binds"])))
                    if sig not in seen:
                        seen.add(sig); states.append(s)
                states = states[:MAX_STATES]
        return states

    def scenes(self, lst, limit):
        """-> list of layer lists, one per distinct path through the event (conditions are not evaluated)."""
        out, seen = [], set()
        for st in self.run(build_nodes(lst), [self.new_state()]):
            layers = st["log"]
            if not layers:
                continue
            # the last moment anything happens; erases after it are just cleanup and are ignored
            hold = max(max([L["d"]] + [L["d"] + m["at"] + m["d"] for m in L["m"]]) for L in layers)
            for L in layers:
                if L["e"] is not None and L["e"] > hold:
                    L["e"] = None
            sig = tuple((l["s"], l["n"], l["x"], l["y"], l["d"], l["e"]) for l in layers)
            if sig not in seen:
                seen.add(sig); out.append(layers)
        out.sort(key=lambda L: -len(L))
        return out[:limit]


# ---------------------------------------------------------------- pictures
def main():
    args, pos, limit, only_list, thumbs, gmode = sys.argv[1:], [], 6, False, True, "name"
    i = 0
    while i < len(args):
        if args[i] == "--max":
            limit = int(args[i + 1]); i += 2; continue
        if args[i] == "--group":
            gmode = args[i + 1]; i += 2; continue
        if args[i] == "--list":
            only_list = True
        elif args[i] == "--no-thumbs":
            thumbs = False
        else:
            pos.append(args[i])
        i += 1
    if len(pos) < 2:
        sys.exit("usage: python rpgm_scenes.py <game folder> <id> [viewer dir] [--list] [--no-thumbs] [--max N]")
    src, gid = pos[:2]
    viewer = pos[2] if len(pos) > 2 else os.path.expanduser("~/pubpets_archive/viewer")
    try:
        from PIL import Image
    except ImportError:
        sys.exit("Pillow is missing: pkg install python-pillow")
    root = find_root(src)
    key = read_key(root)
    W, H, wsrc = screen_size(root)
    print("project:", root, "| screen %dx%d (%s) | encryption key: %s" % (W, H, wsrc, "yes" if key else "none"))

    files = {}
    for r, _, fs in os.walk(os.path.join(root, "img", "pictures")):
        for f in fs:
            if f.lower().endswith(EXTS):
                rel = os.path.relpath(os.path.join(r, f), os.path.join(root, "img", "pictures"))
                files.setdefault(os.path.splitext(rel)[0].replace(os.sep, "/").lower(), os.path.join(r, f))
    print("picture files:", len(files))

    stats = collections.Counter()
    lists = event_lists(root)
    entries = []   # (list info, [layer snapshots])
    for info in lists:
        sim = Sim(stats)
        try:
            snaps = sim.scenes(info["cmds"], limit)
        except RecursionError:
            snaps = []
        entries.append((info, snaps, sorted(sim.calls)))
    print("event lists:", len(lists), "| with pictures:", sum(1 for e in entries if e[1]),
          "| picture buttons bound:", stats["bound"], "of", stats["bindcmd"], "bind commands")

    # resolve picture files + animation cells
    def pic(name):
        return files.get(name.lower())

    def cells_of(L):
        a = L.get("a")
        if not a or a["lay"] != "seq" or not re.search(r"\d\d$", L["n"]):
            return None
        base, start = L["n"][:-2], int(L["n"][-2:])
        names = []
        for k in range(a["n"]):
            nm = "%s%02d" % (base, start + k)
            if not pic(nm):
                break
            names.append(nm)
        return names if len(names) > 1 else None

    missing, scenes, seen = collections.Counter(), [], set()
    for info, snaps, calls in entries:
        if not snaps and not (calls and (info["switches"] or info["kind"] == "common")):
            continue
        for k, layers in enumerate(snaps or [[]]):
            out = []
            for L in layers:
                if not pic(L["n"]):
                    missing[L["n"]] += 1
                    continue
                L = dict(L)
                cs = cells_of(L)
                if cs:
                    L["cells"] = cs
                elif L.get("a") and L["a"]["lay"] == "seq":
                    L.pop("a")
                out.append(L)
            if layers and not out:
                continue
            sig = (info["label"] if not out else "", tuple((l["s"], l["n"], l["x"], l["y"], l["d"], l["e"], l.get("b", {}).get("id")) for l in out))
            if sig in seen:
                continue
            seen.add(sig)
            scenes.append({"info": info, "layers": out, "calls": calls, "k": k, "of": len(snaps)})
    shown = [s for s in scenes if s["layers"]]
    names_needed = set()
    for s in shown:
        for L in s["layers"]:
            for nm in (L.get("cells") or [L["n"]]):
                names_needed.add(nm)
    print("scenes: %d shown (+%d link-only) | distinct pictures to export: %d | pictures not found: %d"
          % (len(shown), len(scenes) - len(shown), len(names_needed), len(missing)))
    if missing:
        print("not found e.g.:", list(missing)[:6])
    gkey = (lambda info: info["gname"]) if gmode == "name" else (lambda info: info["group"])
    cnt = collections.Counter(label(gkey(s["info"])) for s in shown)
    small = {g for g, n in cnt.items() if n < 4 and g != "Other"}

    def tabname(info):
        g = label(gkey(info))
        return "Other" if g in small else g
    if only_list:
        by = collections.Counter(tabname(s["info"]) for s in shown)
        print("tabs (%d):" % len(by), by.most_common(30))
        print("(nothing written)")
        return

    gdir = os.path.join(viewer, "games", gid)
    pdir, sdir = os.path.join(gdir, "pic"), os.path.join(gdir, "scene")
    os.makedirs(pdir, exist_ok=True)
    os.makedirs(sdir, exist_ok=True)
    out_of, sizes, used, nbad = {}, {}, set(), 0
    for n, nm in enumerate(sorted(names_needed), 1):
        fn = slug(nm) + ".webp"
        if fn in used:
            fn = slug(nm) + "_" + hashlib.md5(nm.encode()).hexdigest()[:6] + ".webp"
        used.add(fn)
        try:
            fp = pic(nm)
            im = Image.open(io.BytesIO(decode(open(fp, "rb").read(), fp, key)))
            im.load()
            sizes[nm] = im.size
            im.convert("RGBA").save(os.path.join(pdir, fn), "WEBP", quality=90)
            out_of[nm] = "pic/" + fn
        except Exception as e:
            nbad += 1
        if n % 100 == 0:
            print("  pictures %d / %d" % (n, len(names_needed)))
    print("pictures written: %d | failed: %d" % (len(out_of), nbad))

    def prep(L):
        o = {"s": L["s"], "x": L["x"], "y": L["y"], "n": L["n"]}
        cs = L.get("cells")
        first = (cs or [L["n"]])[0]
        if first not in out_of:
            return None
        o["img"] = out_of[first]
        o["w"], o["h"] = sizes[first]
        if cs:
            if not all(c in out_of for c in cs):
                cs = [c for c in cs if c in out_of]
            o["c"] = [out_of[c] for c in cs]
        if L["o"]:
            o["o"] = L["o"]
        for k, d in (("sx", 100), ("sy", 100), ("op", 255), ("bl", 0)):
            if L[k] != d:
                o[k] = L[k]
        if L["m"]:
            o["m"] = L["m"]
        if L["d"]:
            o["d"] = L["d"]
        if L["e"] is not None:
            o["e"] = L["e"]
        if L.get("a"):
            a = L["a"]
            o["a"] = {"n": a["n"] if not cs else len(cs), "i": a["i"], "lay": a["lay"], "f": a["f"],
                      "go": a.get("go", 0), "t": a.get("t", 1), "loop": a.get("loop", 0)}
            for k in ("p", "cell"):
                if k in a:
                    o["a"][k] = a[k]
        if L.get("b"):
            o["b"] = L["b"]
        return o

    sc_json, groups, by_ce, by_sw = [], collections.OrderedDict(), {}, collections.defaultdict(list)
    for s in scenes:
        layers = [x for x in (prep(L) for L in s["layers"]) if x]
        if s["layers"] and not layers:
            continue
        idx = len(sc_json)
        info = s["info"]
        title = info["label"] + (" (%d/%d)" % (s["k"] + 1, s["of"]) if s["of"] > 1 else "")
        rec = {"t": title, "l": layers}
        if s["calls"]:
            rec["calls"] = s["calls"]
        sc_json.append(rec)
        if info["kind"] == "common" and info["cid"] not in by_ce:
            by_ce[info["cid"]] = idx
        for sw in info["switches"]:
            by_sw[sw].append(idx)
        if layers:
            groups.setdefault(tabname(info), []).append(idx)
            s["idx"] = idx

    # Paper dolls. The game picks pictures by variables (scene T, variant C) and keeps each kind of part in
    # its own picture slot, so one event alone is only a fragment. Here every picture named
    # T<scene>-C<variant>-<part> is stacked in the game's own slot order for each scene/variant.
    DOLL = re.compile(r"^(?:Z-(?:a-)?)?T(\d+)-C?(\d+)-(.+)$")
    cand, rec = collections.defaultdict(collections.Counter), {}
    for s_ in shown:
        for L in s_["layers"]:
            if DOLL.match(L["n"]):
                key = (L["n"], L["s"], L["x"], L["y"], L["sx"], L["sy"], L["op"], L["bl"],
                       json.dumps(L.get("a"), sort_keys=True), tuple(L.get("cells") or []))
                cand[L["n"]][key] += 1
                rec[key] = L
    dolls = collections.defaultdict(list)
    for nm, cnt in cand.items():
        mm = re.search(r"-(\d\d)$", nm)
        if mm and mm.group(1) != "00" and (nm[:-2] + "00") in cand:
            continue                              # a later frame of an animation, not a part of its own
        m = DOLL.match(nm)
        dolls[(int(m.group(1)), int(m.group(2)))].append(rec[cnt.most_common(1)[0][0]])
    doll_items = []
    for key in sorted(dolls):
        layers = []
        for k, L in enumerate(sorted(dolls[key], key=lambda L: (L["s"], L["n"]))):
            L = dict(L)
            L["m"], L["d"], L["e"] = [], 0, None
            L.pop("b", None)
            hidden = L["y"] == 1000               # the game parks parts at y=1000 until it needs them
            if hidden:
                L["y"] = 0
            o = prep(L)
            if not o:
                continue
            o["s"] = L["s"] + k / 1000.0          # unique, keeps the game's slot order
            if hidden:
                o["hid"] = 1                      # parked offscreen by the game (shown, but marked in the panel)
            layers.append(o)
        if len(layers) < 2:
            continue
        idx = len(sc_json)
        sc_json.append({"t": "T%d \u00b7 C%d" % key, "l": layers, "doll": 1})
        shown.append({"idx": idx, "layers": []})
        doll_items.append({"id": "doll%d" % idx, "title": "T%d \u00b7 C%d \u00b7 %d parts" % (key[0], key[1], len(layers)),
                           "thumb": "scene/%d.webp" % idx if thumbs else "", "scene": idx})
    print("paper dolls:", len(doll_items))
    if wsrc == "default":
        # no screen size in the game's files: use the size of the full-screen pictures instead
        full = collections.Counter(tuple(sizes[(L.get("c") or [L["n"]])[0]]) for s_ in shown for L in s_["layers"]
                                   if L["x"] == 0 and L["y"] == 0 and not L["o"] and L["sx"] == 100
                                   and (L.get("c") or [L["n"]])[0] in sizes and sizes[(L.get("c") or [L["n"]])[0]][0] >= 800)
        if full:
            (W, H), _n = full.most_common(1)[0]
            print("screen size not found in the game files, using the full-screen pictures: %dx%d" % (W, H))
    if thumbs:
        TW = 320
        sc = TW / float(W)
        cache = {}

        def small(path):
            # decoded once, already shrunk to thumbnail scale, so the cache stays small
            if path not in cache:
                im = Image.open(os.path.join(gdir, path)).convert("RGBA")
                if len(cache) > 200:
                    cache.clear()
                cache[path] = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))))
            return cache[path]
        for n, s in enumerate(shown, 1):
            if "idx" not in s:
                continue
            canvas = Image.new("RGBA", (TW, int(H * sc)), (42, 42, 48, 255))
            for L in sc_json[s["idx"]]["l"]:
                if L.get("e") is not None:      # erased before the end: not part of the final picture
                    continue
                try:
                    im = small((L.get("c") or [L["img"]])[0])
                    a = L.get("a")
                    if a and a["lay"] == "v":
                        im = im.crop((0, 0, im.width, max(1, im.height // a["n"])))
                    elif a and a["lay"] == "h":
                        im = im.crop((0, 0, max(1, im.width // a["n"]), im.height))
                    zx, zy = L.get("sx", 100) / 100.0, L.get("sy", 100) / 100.0
                    if (zx, zy) != (1.0, 1.0):
                        im = im.resize((max(1, int(im.width * zx)), max(1, int(im.height * zy))))
                    px, py = L["x"] * sc, L["y"] * sc
                    if L.get("o"):
                        px -= im.width / 2.0
                        py -= im.height / 2.0
                    if L.get("op", 255) < 255:
                        im = im.copy()
                        im.putalpha(im.getchannel("A").point(lambda v, o=L["op"]: v * o // 255))
                    canvas.paste(im, (int(px), int(py)), im)
                except Exception:
                    pass
            canvas.convert("RGB").save(os.path.join(sdir, "%d.webp" % s["idx"]), "WEBP", quality=70)
            if n % 200 == 0:
                print("  thumbnails %d / %d" % (n, len(shown)))

    tabs, ngroup = [], 0
    for g, idxs in sorted(groups.items(), key=lambda kv: (kv[0] == "Other", -len(kv[1]))):
        name = g.strip()
        if has_jp(name):                      # no English label known: number it
            ngroup += 1
            name = "Group %d" % ngroup
        items = []
        for n, i in enumerate(idxs, 1):
            sc_json[i]["jp"] = sc_json[i]["t"]   # original event label, kept for reference
            sc_json[i]["t"] = "%s #%d" % (name, n)
            items.append({"id": "sc%d" % i, "title": sc_json[i]["t"],
                          "thumb": "scene/%d.webp" % i if thumbs else "", "scene": i})
        tabs.append({"name": "\u25B6 " + name, "items": items})
    if doll_items:
        tabs.insert(0, {"name": "\u25B6 Paper dolls", "items": doll_items})
    with open(os.path.join(gdir, "scenes.json"), "w", encoding="utf-8") as fh:
        json.dump({"w": W, "h": H, "scenes": sc_json, "byCE": by_ce, "bySw": by_sw, "groups": tabs}, fh,
                  ensure_ascii=False, separators=(",", ":"))
    print("wrote", os.path.join(gdir, "scenes.json"), "| tabs:", [(t["name"], len(t["items"])) for t in tabs][:12])


if __name__ == "__main__":
    main()
