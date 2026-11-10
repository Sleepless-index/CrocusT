# First look at an unpacked Unity game: backend, Spine files and versions,
# CG-looking art, audio, Addressables. Works on a Windows build folder or an
# unzipped apk.   python inspect_unity.py <folder that contains the game>
import platform, sys, os, re, collections
from unittest.mock import MagicMock

def main():
    platform.system = lambda: "Linux"
    sys.platform = "linux"
    for m in ("fmod_toolkit", "fmod_toolkit.libfmod", "pyfmodex"):
        sys.modules[m] = MagicMock()
    import UnityPy

    root = sys.argv[1] if len(sys.argv) > 1 else "."
    datas = [r for r, d, f in os.walk(root) if os.path.basename(r).endswith("_Data")
             and any(x in f for x in ("globalgamemanagers", "data.unity3d", "globalgamemanagers.assets"))]
    if not datas:
        datas = [os.path.join(root, "assets", "bin", "Data")] if os.path.isdir(os.path.join(root, "assets")) else [root]
    print("data folder(s):", datas)
    for dd in datas:
        up = os.path.dirname(dd)
        print("  Mono backend (Managed/Assembly-CSharp.dll):", os.path.exists(os.path.join(dd, "Managed", "Assembly-CSharp.dll")),
              "| IL2CPP:", os.path.exists(os.path.join(up, "GameAssembly.dll")) or os.path.exists(os.path.join(dd, "il2cpp_data")))
        files = []
        for r, _, fs in os.walk(dd):
            for f in fs:
                p = os.path.join(r, f)
                files.append((os.path.getsize(p), os.path.relpath(p, dd)))
        files.sort(reverse=True)
        print("  biggest files:", [(n, round(s / 1e6)) for s, n in files[:12]])
        sa = os.path.join(dd, "StreamingAssets")
        if os.path.isdir(sa):
            bundles = [n for s, n in files if n.endswith((".bundle", ".unity3d"))]
            print("  StreamingAssets:", os.listdir(sa)[:12], "| bundles:", len(bundles))

    pat = re.compile(r"^(level\d+|globalgamemanagers(\.assets)?|resources\.assets|sharedassets\d+\.assets|data\.unity3d)$")
    cand = []
    for dd in datas:
        for r, _, fs in os.walk(dd):
            for f in fs:
                if pat.match(f) or f.endswith((".bundle", ".unity3d")):
                    cand.append(os.path.join(r, f))
    print("\nloadable unity files:", len(cand))

    types = collections.Counter()
    tex, spine_json, atlas, binskel = [], [], [], []
    versions = collections.Counter()
    audio = []
    failed, unity_ver, mono_ok, mono_n = 0, None, 0, 0
    for p in cand:
        try:
            env = UnityPy.load(p)
        except Exception:
            failed += 1
            continue
        for o in env.objects:
            t = o.type.name
            types[t] += 1
            if unity_ver is None:
                unity_ver = str(getattr(o.assets_file, "unity_version", ""))
            try:
                if t in ("Texture2D", "Sprite"):
                    d = o.read()
                    tex.append((t, d.m_Name, getattr(d, "m_Width", 0), getattr(d, "m_Height", 0)))
                elif t == "AudioClip":
                    audio.append(o.read().m_Name)
                elif t == "TextAsset":
                    d = o.read()
                    s = d.m_Script
                    b = s.encode("utf-8", "surrogateescape") if isinstance(s, str) else bytes(s)
                    head = b[:3000]
                    mv = re.search(rb'"spine"\s*:\s*"([^"]+)"', head)
                    if b[:1] == b"{" and mv:
                        spine_json.append(d.m_Name); versions[mv.group(1).decode()] += 1
                    elif b"size:" in b[:600] and b"filter:" in b[:600]:
                        atlas.append(d.m_Name)
                    elif d.m_Name.lower().endswith(".skel") or (len(b) > 200 and re.search(rb"\x00?[34]\.\d\.\d{1,3}", b[:80]) and b"\n" not in b[:40]):
                        mv = re.search(rb"[34]\.\d\.\d{1,3}", b[:80])
                        binskel.append(d.m_Name)
                        if mv: versions["binary " + mv.group(0).decode()] += 1
                elif t == "MonoBehaviour" and mono_n < 40:
                    mono_n += 1
                    try:
                        o.read_typetree(); mono_ok += 1
                    except Exception:
                        pass
            except Exception:
                pass
    print("files that failed to load:", failed, "| Unity version:", unity_ver)
    print("object types:", types.most_common(14))
    print("MonoBehaviour type info readable:", mono_ok, "of", mono_n, "tested")
    print("\nSPINE json skeletons:", len(spine_json), "| binary skeletons:", len(binskel), "| atlases:", len(atlas))
    print("spine versions:", dict(versions))
    print("sample skeleton names:", (spine_json + binskel)[:14])
    print("sample atlas names:", atlas[:8])
    big = sorted([x for x in tex if x[0] == "Texture2D"], key=lambda x: -x[2] * x[3])[:12]
    print("\nlargest textures:", [(n, w, h) for _, n, w, h in big])
    cg = [n for _, n, _, _ in tex if re.search(r"cg|scene|event|gallery|thumb", n, re.I)]
    print("names that look like CG/gallery art:", len(cg), sorted(set(cg))[:24])
    print("audio clips:", len(audio), "| sample:", audio[:10])

if __name__ == "__main__":
    main()
