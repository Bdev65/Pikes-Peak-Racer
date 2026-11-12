# Pikes Peak Racer

A first-person hill climb driving game for the phone browser: the Pikes Peak International Hill Climb course,
about 12.3 miles and 4,700 ft of climb, in a single self-contained HTML file with no network requests.

**Play:** open the GitHub Pages link for this repo on a phone (landscape works best) or a computer.

## Controls
- Drag on the left half of the screen to steer.
- Right side: brake and gas pedals; press higher for more.
- Hold the brake at a standstill for reverse. − / + change the cockpit zoom.
- Keyboard: arrows or WASD, Z / X to shift, R to reset.

Best times are saved in each player's own browser.

## Course data
The built-in course is an approximation of the real road (length, climb, turn count and section character),
not a survey. Load a real GPX file from the in-game menu, or replace the `COURSE` array.

## Real course data
`tools/fetch_course.py` pulls the real road from OpenStreetMap and the terrain from the USGS 3D Elevation
Program, and saves them in `data/` (see `data/report.md`). It runs on GitHub's servers through the
"Fetch course data" workflow: Actions tab → Fetch course data → Run workflow.

Road data © OpenStreetMap contributors, available under the Open Database License.
Elevation data: U.S. Geological Survey, 3D Elevation Program (public domain).

## Files
- `index.html` — the game (built file; this is what GitHub Pages serves)
- `src/template.html` — game source, with placeholders for the course data
- `src/gen.js` — generates the built-in course (`course.json`, `landmarks.json`)
- `src/build.js` — run `node src/build.js` to rebuild `index.html` from the source
