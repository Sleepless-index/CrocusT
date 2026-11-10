import platform, sys
platform.system = lambda: "Linux"
sys.platform = "linux"
import UnityPy, os
names = set()
for root, _, files in os.walk("assets"):
    for f in files:
        if f.endswith((".dat", ".json", ".resource")) or f == "boot.config":
            continue
        try:
            for o in UnityPy.load(os.path.join(root, f)).objects:
                if o.type.name == "AnimationClip":
                    names.add(o.read().m_Name)
        except Exception:
            pass
open("clips.txt", "w").write("\n".join(sorted(names)))
print(len(names), "clips")
