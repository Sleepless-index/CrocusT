PubPets CG archive
viewer/      spine viewer: bash viewer/run.sh, then open http://localhost:8000
             (Spine 4.2.40 runtime is bundled, so it works offline)
             viewer/cg has every .json, .atlas and texture page
cg_sorted/   spine_pages/ = the 56 textures the spine atlases use
             other/ = the other 368 (UI, thumbnails, AVG art, batai, SD, backgrounds)
ta_out/      all dumped TextAssets (spine json/atlas plus dialogue .bin files)
tools/       the python scripts used (ext.py, ta.py, fixpages.py, audit.py ...)
Notes: ALS-8 is Alice CG 8 (no ailisi8). Anto CG 1-3 are Anto_CG_01-03, CG 4-10 are antuo4-10.
Needs: pkg install python
viewer/audio = sounds extracted from the APK (68 files), played by the viewer on spine events. Scripts: tools/audio_*.py
Ren'Py games: python tools/extract_renpy.py <game.zip or folder> <id> "<Title>" viewer   (needs: pkg install python-pillow; stills only, no Spine)

Removing a game
  Run these from the repo folder (the one that contains viewer/ and tools/).
  Replace ID with the game's id, which is its folder name in viewer/games/ and its "id" in viewer/games.json.
  1. Remove it from the picker (this is the step that hides it):
       python -c "import json;p='viewer/games.json';d=[g for g in json.load(open(p)) if g['id']!='ID'];json.dump(d,open(p,'w'),indent=1)"
  2. Delete its files (game.json, images.json and the local art):
       rm -rf viewer/games/ID
  3. Commit and push the change:
       git add -A && git commit -m "Remove ID" && git push
  4. Optional, free space in your art backup zip:
       zip -d ~/storage/downloads/crocus_art.zip "viewer/games/ID/*"
  Do both 1 and 2. If you delete the folder but leave the games.json entry, the picker shows a broken tile.
  If you only want to hide a game for now, do step 1 and skip step 2. Add the entry back to games.json to show it again.
  Reload the page afterwards (a hard refresh, or clear the site data if the old picker is still shown).
