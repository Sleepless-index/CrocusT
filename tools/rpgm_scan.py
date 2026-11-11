# Read an RPG Maker MV/MZ game's event data and report how it stacks its pictures:
# which picture slot (layer) each kind of picture uses, where it is placed, and which
# plugins are on. Writes nothing. Run it, then paste the output back.
#   python rpgm_scan.py <unpacked game folder>                  overview
#   python rpgm_scan.py <unpacked game folder> --name T0-C0-F0006   also show the event commands around that picture
#   python rpgm_scan.py <unpacked game folder> --seq               also show the busiest picture sequence
#   python rpgm_scan.py <unpacked game folder> --grep T0-C0       find any command (script, plugin, text...) containing that text
#   python rpgm_scan.py <unpacked game folder> --plugin PictureAnimation   print that plugin's help text
import sys, os, re, json, collections

CODES = {101: "Text", 108: "Comment", 408: "Comment+", 111: "If", 112: "Loop", 113: "BreakLoop", 115: "ExitEvt",
         117: "CallCommon", 118: "Label", 119: "Goto", 121: "Switch", 122: "Variable", 123: "SelfSwitch",
         201: "Transfer", 230: "Wait", 231: "ShowPic", 232: "MovePic", 233: "RotatePic", 234: "TintPic",
         235: "ErasePic", 355: "Script", 655: "Script+", 356: "PluginCmd", 357: "PluginCmdMZ", 411: "Else",
         412: "EndIf", 413: "Repeat", 402: "Choice", 403: "ChoiceCancel", 404: "EndChoice", 102: "Choices"}
PIC = re.compile(r"^(?:Z-(?:a-)?)?T(\d+)-C(\d+)-([A-Za-z]+)(\d+)")


def find_root(path):
    for r, dirs, files in os.walk(path):
        if os.path.isdir(os.path.join(r, "img")) and os.path.isfile(os.path.join(r, "data", "System.json")):
            return r
    sys.exit("No RPG Maker project (img/ + data/System.json) under " + path)


def jload(p):
    with open(p, encoding="utf-8-sig") as fh:
        return json.load(fh)


def lists_of(root):
    d = os.path.join(root, "data")
    out = []
    p = os.path.join(d, "CommonEvents.json")
    if os.path.exists(p):
        for e in jload(p):
            if e:
                out.append(("Common %s '%s'" % (e["id"], e.get("name", "")), e["list"]))
    for f in sorted(os.listdir(d)):
        if re.match(r"Map\d+\.json$", f):
            try:
                m = jload(os.path.join(d, f))
            except Exception:
                continue
            for e in m.get("events") or []:
                if not e:
                    continue
                for i, pg in enumerate(e.get("pages") or []):
                    out.append(("%s ev%s '%s' p%d" % (f[:-5], e["id"], e.get("name", ""), i + 1), pg.get("list") or []))
    return out


def short(v):
    s = json.dumps(v, ensure_ascii=False)
    return s if len(s) < 90 else s[:87] + "..."


def show_cmd(c):
    return "%s%s %s" % ("  " * (c.get("indent", 0)), CODES.get(c["code"], c["code"]), short(c["parameters"]))


def top(counter, n=5):
    return ", ".join("%s x%d" % (k, v) for k, v in counter.most_common(n))


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit("usage: python rpgm_scan.py <game folder> [--name PICTURE] [--seq]")
    root = find_root(a[0])
    name = a[a.index("--name") + 1] if "--name" in a else None
    grep = a[a.index("--grep") + 1] if "--grep" in a else None
    plugin = a[a.index("--plugin") + 1] if "--plugin" in a else None
    seq = "--seq" in a
    lists = lists_of(root)
    print("project:", root)
    if plugin:
        pf = os.path.join(root, "js", "plugins", plugin + ".js")
        try:
            txt = open(pf, encoding="utf-8-sig", errors="replace").read()
            m = re.search(r"/\*:(?!ja)(.*?)\*/", txt, re.S) or re.search(r"/\*:ja(.*?)\*/", txt, re.S)
            body = (m.group(1) if m else txt[:4000]).strip().splitlines()
            print("--- %s help (first 80 lines of %d)" % (plugin, len(body)))
            print("\n".join(l.rstrip() for l in body[:80]))
        except Exception as e:
            print("could not read", pf, e)
        return
    print("command lists:", len(lists))
    pj = os.path.join(root, "js", "plugins.js")
    try:
        txt = open(pj, encoding="utf-8-sig").read()
        on = re.findall(r'"name"\s*:\s*"([^"]+)"\s*,\s*"status"\s*:\s*(true|false)', txt)
        print("plugins on:", ", ".join(n for n, st in on if st == "true"))
    except Exception as e:
        print("plugins: could not read", e)

    codes = collections.Counter()
    shows = []   # (label, list, idx, params)
    plug = collections.Counter()
    pfirst, scr, hits = collections.Counter(), collections.Counter(), []
    for label, lst in lists:
        for i, c in enumerate(lst):
            codes[c["code"]] += 1
            if c["code"] == 356 and c["parameters"]:
                pfirst[str(c["parameters"][0]).split(" ")[0]] += 1
            if c["code"] in (355, 655) and c["parameters"] and re.search(r"pic|Pic", str(c["parameters"][0])):
                scr[re.sub(r"\d+", "N", str(c["parameters"][0]))[:120]] += 1
            if grep and grep.lower() in json.dumps(c["parameters"], ensure_ascii=False).lower():
                hits.append((label, lst, i))
            if c["code"] == 231:
                shows.append((label, lst, i, c["parameters"]))
            elif c["code"] in (356, 357) and re.search(r"pic|anim|layer|cg", json.dumps(c["parameters"]), re.I):
                plug[re.sub(r"\d+", "N", json.dumps(c["parameters"], ensure_ascii=False))[:110]] += 1
    print("commands:", {CODES.get(k, k): v for k, v in codes.most_common() if k in CODES and k in (230, 231, 232, 233, 234, 235, 117, 356, 357, 355, 111)})
    print("show-picture commands:", len(shows), "| distinct names:", len({s[3][1] for s in shows}))
    if plug:
        print("plugin commands mentioning pictures:")
        for k, v in plug.most_common(8):
            print("  x%d %s" % (v, k))

    print("plugin command words:", top(pfirst, 25))
    if scr:
        print("script lines mentioning pictures:")
        for k, v in scr.most_common(10):
            print("  x%d %s" % (v, k))
    if grep:
        print("\n--- commands containing '%s': %d" % (grep, len(hits)))
        for label, lst, i in hits[:4]:
            print("[%s] command #%d" % (label, i))
            for j in range(max(0, i - 4), min(len(lst), i + 5)):
                print("%s %4d %s" % (">>" if j == i else "  ", j, show_cmd(lst[j])))

    byletter, bycn = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
    place = collections.defaultdict(collections.Counter)
    odd = collections.Counter()
    for label, lst, i, p in shows:
        pid, nm = p[0], p[1]
        m = PIC.match(str(nm))
        if not m:
            odd[(pid, str(nm)[:20])] += 1
            continue
        letter = m.group(3).upper()
        byletter[letter][pid] += 1
        bycn["C" + m.group(2)][pid] += 1
        place[letter][(p[2], p[3], p[4], p[5], p[6], p[7], p[8], p[9])] += 1
    print("\nslot (layer number) used by picture kind  [names like T4-C0-F0010-00 -> kind F]:")
    for k in sorted(byletter):
        print("  kind %s: slots %s" % (k, top(byletter[k], 6)))
    print("by C number:")
    for k in sorted(bycn, key=lambda x: int(x[1:])):
        print("  %s: slots %s" % (k, top(bycn[k], 6)))
    print("placement (origin,designation,x,y,scaleX,scaleY,opacity,blend):")
    for k in sorted(place):
        print("  kind %s: %s" % (k, top(place[k], 3)))
    if odd:
        print("other pictures (slot,name):", top(odd, 8))

    if name:
        print("\n--- where '%s' is shown" % name)
        n = 0
        for label, lst, i, p in shows:
            if name.lower() in str(p[1]).lower():
                n += 1
                if n > 2:
                    break
                print("[%s] command #%d" % (label, i))
                for j in range(max(0, i - 8), min(len(lst), i + 9)):
                    print("%s %4d %s" % (">>" if j == i else "  ", j, show_cmd(lst[j])))
        if n == 0:
            print("no show-picture command uses that name (it may be set by a plugin or variable)")
    if seq and shows:
        cnt = collections.Counter(id(s[1]) for s in shows)
        best = max(shows, key=lambda s: cnt[id(s[1])])
        print("\n--- busiest list: %s (%d show commands). Picture-related commands only:" % (best[0], cnt[id(best[1])]))
        k = 0
        for j, c in enumerate(best[1]):
            if c["code"] in (230, 231, 232, 235, 117, 111, 356, 357, 118, 119):
                print("%4d %s" % (j, show_cmd(c)))
                k += 1
                if k >= 45:
                    print("   ...")
                    break


if __name__ == "__main__":
    main()
