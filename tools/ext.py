import platform, sys, traceback
from unittest.mock import MagicMock
platform.system = lambda: "Linux"
sys.platform = "linux"
for m in ("fmod_toolkit", "fmod_toolkit.libfmod", "pyfmodex"):
    sys.modules[m] = MagicMock()
import os
import UnityPy
import UnityPy.classes.legacy_patch.Texture2D as T

DATA = os.path.abspath("assets/bin/Data")

def my_get(*args, **kw):
    path = args[0]
    offset, size = args[-2], args[-1]
    p = os.path.join(DATA, os.path.basename(path))
    with open(p, "rb") as fh:
        fh.seek(offset)
        return fh.read(size)

T.get_resource_data = my_get

out = "cg_out"; os.makedirs(out, exist_ok=True)
seen = set(); errs = 0
for root, _, files in os.walk("assets"):
    for f in files:
        if f.endswith((".dat", ".json", ".resource")) or f == "boot.config":
            continue
        try:
            env = UnityPy.load(os.path.join(root, f))
        except Exception:
            continue
        for o in env.objects:
            if o.type.name == "Texture2D":
                try:
                    d = o.read()
                    n = d.m_Name or str(o.path_id)
                    if n in seen: continue
                    d.image.save(f"{out}/{n}.png")
                    seen.add(n)
                except Exception:
                    errs += 1
                    if errs == 1: traceback.print_exc()
print(len(seen), "saved,", errs, "failed")
