import UnityPy, os, collections
c = collections.Counter()
for root, _, files in os.walk("assets"):
    for f in files:
        p = os.path.join(root, f)
        if f.endswith((".dat", ".json", ".dll-resources.dat")) or f == "boot.config":
            continue
        try:
            for o in UnityPy.load(p).objects:
                c[o.type.name] += 1
        except Exception as e:
            print("skip", f, e)
print(c.most_common(25))
