import os
from PIL import Image

tex = {f[:-4]: f for f in os.listdir("cg_out") if f.endswith(".png")}
ta = os.listdir("ta_out")
spines = {f[:-len(".spine.json")].strip() for f in ta if f.endswith(".spine.json")}
atlas_files = {f[:-len(".atlas.atlas")].strip(): f for f in ta if f.endswith(".atlas.atlas")}

pages = {}
for name, f in atlas_files.items():
    lines = open("ta_out/" + f, encoding="utf-8", errors="ignore").read().splitlines()
    pages[name] = [os.path.splitext(os.path.basename(l.strip()))[0]
                   for l in lines if l.strip().lower().endswith(".png")]
used = {p for v in pages.values() for p in v}

def yn(b): return "yes" if b else "NO "

print("== Expected CG slots ==")
slots = [f"hedi{i}" for i in range(1, 11)] + [f"ailisi{i}" for i in range(1, 11)] \
      + [f"antuo{i}" for i in range(1, 11)] + [f"Anto_CG_{i:02d}" for i in range(1, 4)]
for s in slots:
    pg = pages.get(s, [])
    ok = all(p in tex for p in pg) if pg else False
    print(f"{s:12} spine={yn(s in spines)} atlas={yn(s in atlas_files)} pages_ok={yn(ok)}")

print("\n== Spine without atlas / atlas without spine ==")
for s in sorted(spines - set(atlas_files)): print("spine only:", s)
for s in sorted(set(atlas_files) - spines): print("atlas only:", s)

print("\n== Atlas pages with no extracted PNG ==")
for n, v in pages.items():
    for p in v:
        if p not in tex: print(n, "->", p)

print("\n== Large textures not used by any atlas (possible unused CG art) ==")
rows = []
for name, f in tex.items():
    if name in used: continue
    try:
        w, h = Image.open("cg_out/" + f).size
    except Exception:
        continue
    if max(w, h) >= 1000: rows.append((w * h, name, w, h))
for _, name, w, h in sorted(rows, reverse=True)[:40]:
    print(f"{name} {w}x{h}")
