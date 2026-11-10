import platform, sys
from unittest.mock import MagicMock
platform.system = lambda: "Linux"
sys.platform = "linux"
for m in ("fmod_toolkit", "fmod_toolkit.libfmod", "pyfmodex"):
    sys.modules[m] = MagicMock()
import UnityPy, os
out = "ta_out"; os.makedirs(out, exist_ok=True)
n = 0
for root, _, files in os.walk("assets"):
    for f in files:
        if f.endswith((".dat", ".json", ".resource")) or f == "boot.config":
            continue
        try:
            env = UnityPy.load(os.path.join(root, f))
        except Exception:
            continue
        for o in env.objects:
            if o.type.name != "TextAsset":
                continue
            try:
                d = o.read()
                s = d.m_Script
                b = s.encode("utf-8", "surrogateescape") if isinstance(s, str) else bytes(s)
                head = b[:600]
                if b"size:" in head and b"filter:" in head: ext = "atlas"
                elif b[:1] == b"{" and b'"bones"' in b[:3000]: ext = "spine.json"
                elif b[:1] == b"{": ext = "json"
                else: ext = "bin"
                open(f"{out}/{d.m_Name}.{ext}", "wb").write(b)
                n += 1
            except Exception as e:
                print("skip", e)
print(n, "dumped")
