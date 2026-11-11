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
