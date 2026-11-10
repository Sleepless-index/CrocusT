import os, re, collections
from PIL import Image
d = "cg_out"
groups = collections.defaultdict(list)
for f in os.listdir(d):
    m = re.match(r"(.+?)(?:_(\d+))?\.png$", f)
    if m and re.match(r"(hedi|ailisi|antuo|Anto_CG|batai)", f, re.I):
        groups[m.group(1)].append((int(m.group(2) or 1), f))
os.makedirs("gifs", exist_ok=True)
for base, items in groups.items():
    if len(items) < 2: continue
    items.sort()
    frames = [Image.open(f"{d}/{f}").convert("RGBA") for _, f in items]
    size = frames[0].size
    frames = [fr.resize(size) for fr in frames]
    frames[0].save(f"gifs/{base}.gif", save_all=True, append_images=frames[1:], duration=150, loop=0, disposal=2)
    print(base, len(frames), "frames")
