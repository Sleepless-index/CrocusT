import os, re
from PIL import Image
for f in sorted(os.listdir("viewer/cg")):
    if not f.endswith(".atlas"): continue
    pages = []
    lines = open("viewer/cg/" + f, encoding="utf-8", errors="ignore").read().splitlines()
    for i, l in enumerate(lines):
        if l.strip().lower().endswith(".png"):
            sz = lines[i+1].strip() if i + 1 < len(lines) else ""
            pages.append((l.strip(), sz))
    for name, sz in pages:
        base = os.path.splitext(os.path.basename(name))[0]
        p = "cg_out/" + base + ".png"
        have = Image.open(p).size if os.path.exists(p) else "MISSING"
        print(f, name, sz, "->", have)
