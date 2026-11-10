# Lists the images in an unpacked Unity game grouped by name pattern, to find the
# static CGs / backgrounds that are not Spine files.
#   python list_images.py <unpacked game folder>
import platform, sys, os, re, collections
from unittest.mock import MagicMock

def pattern(name):
    return re.sub(r"\d+", "#", name)

def main():
    platform.system = lambda: "Linux"
    sys.platform = "linux"
    for m in ("fmod_toolkit", "fmod_toolkit.libfmod", "pyfmodex"):
        sys.modules[m] = MagicMock()
    import UnityPy
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    datas = [r for r, d, f in os.walk(root) if os.path.basename(r).endswith("_Data")
             and any(x in f for x in ("globalgamemanagers", "data.unity3d"))]
    if not datas:
        sys.exit("No *_Data folder found under " + root)
    pat = re.compile(r"^(level\d+|globalgamemanagers(\.assets)?|resources\.assets|sharedassets\d+\.assets)$")
    files = [os.path.join(datas[0], f) for f in sorted(os.listdir(datas[0])) if pat.match(f)]
    items = []
    for p in files:
        try:
            env = UnityPy.load(p)
        except Exception:
            continue
        for o in env.objects:
            if o.type.name not in ("Texture2D", "Sprite"):
                continue
            try:
                d = o.read()
                if o.type.name == "Texture2D":
                    w, h = d.m_Width, d.m_Height
                else:
                    r = d.m_Rect
                    w, h = int(r.width), int(r.height)
                items.append((o.type.name, d.m_Name, w, h))
            except Exception:
                pass
    print(len(items), "images")
    groups = collections.defaultdict(list)
    for t, n, w, h in items:
        groups[(t, pattern(n))].append((n, w, h))
    rows = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    print("\nname patterns (type, pattern, how many, example, biggest size):")
    for (t, pat_), v in rows[:45]:
        big = max(v, key=lambda x: x[1] * x[2])
        print(" ", t[:3], pat_[:44], len(v), "e.g.", v[0][0][:32], "| max", big[1], "x", big[2])
    ep = [(t, n, w, h) for t, n, w, h in items if re.search(r"ep0?2|ep_?2", n, re.I)]
    print("\nimages with ep2 in the name:", len(ep), "| sample:", [n for _, n, _, _ in ep[:14]])
    large = [(n, w, h) for t, n, w, h in items if t == "Texture2D" and max(w, h) >= 1400 and not n.startswith("sactx")]
    print("\nlarge standalone textures (", len(large), "):", sorted({n for n, _, _ in large})[:40])

if __name__ == "__main__":
    main()
