import os, shutil
n = 0
for f in os.listdir("viewer/cg"):
    if not f.endswith(".atlas"): continue
    for l in open("viewer/cg/" + f, encoding="utf-8", errors="ignore").read().splitlines():
        if l.strip().lower().endswith(".png"):
            base = os.path.splitext(os.path.basename(l.strip()))[0]
            src = "cg_out/" + base + ".png"
            if os.path.exists(src):
                shutil.copy(src, "viewer/cg/" + base + ".png"); n += 1
            else:
                print("missing:", base)
print(n, "pages copied")
