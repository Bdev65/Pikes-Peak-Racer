# Pikes Peak Racer

A first-person hill climb driving game for the phone browser: the Pikes Peak International Hill Climb course,
12.42 miles and 4,700 ft of climb on the real road and terrain, in a single self-contained HTML file with no
network requests.

**Play:** open the GitHub Pages link for this repo on a phone (landscape works best) or a computer.

## Controls
- Drag on the left half of the screen to steer.
- Right side: brake and gas pedals; press higher for more.
- Hold the brake at a standstill for reverse. − / + change the cockpit zoom.
- Keyboard: arrows or WASD, Z / X to shift, R to reset.

Best times are saved in each player's own browser.

## Course data
The built-in course is the real Pikes Peak Highway from the hill climb start line to the summit, drawn on
real terrain. `tools/fetch_course.py` pulls the road and named places from OpenStreetMap and the elevation
from the USGS 3D Elevation Program and saves them in `data/` (see `data/report.md`). It runs on GitHub's
servers through the "Fetch course data" workflow: Actions tab → Fetch course data → Run workflow.
`node src/build.js` then bakes `data/` into `index.html`.

You can still load your own GPX from the in-game menu. A course inside the terrain grid is drawn on the real
mountain; anywhere else the hillsides are generated from the road.

Road data © OpenStreetMap contributors, available under the Open Database License.
Elevation data: U.S. Geological Survey, 3D Elevation Program (public domain).

## Files
- `index.html` — the game (built file; this is what GitHub Pages serves)
- `src/template.html` — game source, with placeholders for the course data
- `src/build.js` — run `node src/build.js` to rebuild `index.html` from the source and `data/`
- `tools/fetch_course.py` — fetches the road, terrain and landmarks into `data/`
