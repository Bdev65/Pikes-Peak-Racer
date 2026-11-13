// Builds ../index.html from template.html and the fetched data in ../data (see tools/fetch_course.py).
const fs = require('fs'), d = __dirname, data = d + '/../data/';
const MI = 1609.344;
let t = fs.readFileSync(d + '/template.html', 'utf8');
const course = JSON.parse(fs.readFileSync(data + 'course.json', 'utf8'));
const places = fs.existsSync(data + 'places.json') ? JSON.parse(fs.readFileSync(data + 'places.json', 'utf8')) : [];

// ---- start line. The race starts at the highway's Mile 7 marker. OpenStreetMap has the Mile 8 marker but not Mile 7,
// so the line is placed one mile of road below Mile 8. The game draws its start line 40 m into the course, so the
// course is trimmed to begin 40 m before that point (this also drops the junction stub at the very start of the fetched road).
const LEAD = 40; let TRIM = 0;
(function () {
  const m8 = places.find(p => p.tags.highway === 'milestone' && p.tags.distance === '8 mi'); if (!m8) { console.log('no Mile 8 marker: start line left at the start of the data'); return; }
  const startM = (m8.mile - 1) * MI, trim = startM - LEAD; if (!(trim > 0)) return;
  const k = 111320 * Math.cos(course[0][0] * Math.PI / 180), dist = (a, b) => Math.hypot((b[1] - a[1]) * k, (b[0] - a[0]) * 111132);
  let acc = 0, i = 1; for (; i < course.length; i++) { const d = dist(course[i - 1], course[i]); if (acc + d >= trim) { const f = (trim - acc) / d, a = course[i - 1], b = course[i]; course.splice(0, i, [+(a[0] + f * (b[0] - a[0])).toFixed(6), +(a[1] + f * (b[1] - a[1])).toFixed(6), +(a[2] + f * (b[2] - a[2])).toFixed(1)]); break; } acc += d; }
  for (const p of places) p.mile = +(p.mile - trim / MI).toFixed(3);
  TRIM = trim;
  let len = 0; for (let q = 1; q < course.length; q++) len += dist(course[q - 1], course[q]);
  console.log('start line at ' + (startM / MI).toFixed(3) + ' mi of the fetched road; course trimmed by ' + Math.round(trim) + ' m; start to end of road ' + ((len - LEAD) / 1000).toFixed(2) + ' km; first point', course[0]);
})();

// ---- landmarks: only names whose position comes from the data
const lm = [];
const pick = (name, test) => { const c = places.filter(p => p.name === name && (!test || test(p))).sort((a, b) => a.off_m - b.off_m)[0]; return c ? c.mile : null; };
for (const [name, label, start, test] of [
  ['Halfway Picnic Grounds', 'Halfway Picnic Grounds', 1], ['Glen Cove', 'Glen Cove', 1, p => p.tags.place],
  ["Devil's Playground", "Devil's Playground", 1, p => p.tags.amenity], ['Little Pikes Peak', 'Little Pikes Peak', 0], ['Boulder Park', 'Boulder Park', 1]]) {
  const m = pick(name, test); if (m != null) lm.push([m, label, start]);
}
for (const p of places) if (p.mile > 0.05 && p.tags.highway === 'milestone' && /^\d+ mi$/.test(p.tags.distance || '')) lm.push([p.mile, 'Mile ' + parseInt(p.tags.distance) + (p.name ? ' · ' + p.name : ''), 0]);
// A practice start at the first stack of hairpins between Glen Cove and Devil's Playground, found from the road shape
(function () {
  const lo = pick('Glen Cove', p => p.tags.place), hi = pick("Devil's Playground", p => p.tags.amenity); if (lo == null || hi == null) return;
  const k = 111320 * Math.cos(course[0][0] * Math.PI / 180), xy = course.map(p => [(p[1] - course[0][1]) * k, (p[0] - course[0][0]) * 111132]);
  const rs = [xy[0]], dist = [0]; let acc = 0, tot = 0;
  for (let i = 1; i < xy.length; i++) { const s = Math.hypot(xy[i][0] - xy[i - 1][0], xy[i][1] - xy[i - 1][1]); acc += s; tot += s; if (acc >= 10) { rs.push(xy[i]); dist.push(tot); acc = 0; } }
  const hd = []; for (let i = 1; i < rs.length; i++) hd.push(Math.atan2(rs[i][0] - rs[i - 1][0], rs[i][1] - rs[i - 1][1]));
  const hair = [];
  for (let i = 0; i + 8 < hd.length; i++) { let s = 0; for (let q = i; q < i + 8; q++) { let a = hd[q + 1] - hd[q]; a = Math.atan2(Math.sin(a), Math.cos(a)); s += a; }
    const m = dist[i + 4] / MI; if (Math.abs(s) > 2.3 && m > lo && m < hi && (!hair.length || m - hair[hair.length - 1] > 0.08)) hair.push(m); }
  for (let i = 0; i < hair.length; i++) if (hair.filter(m => m >= hair[i] && m < hair[i] + 0.5).length >= 3) { lm.push([+(hair[i] - 0.06).toFixed(3), 'The switchbacks', 1]); break; }
  console.log('hairpins between Glen Cove and Devil\'s Playground at miles', hair.map(m => m.toFixed(2)).join(', '));
})();
lm.sort((a, b) => a[0] - b[0]);
console.log(lm.map(l => l[0].toFixed(2) + '  ' + l[1] + (l[2] ? '  [start]' : '')).join('\n'));

// ---- terrain
let terrain = 'null';
if (fs.existsSync(data + 'terrain.bin')) {
  const h = JSON.parse(fs.readFileSync(data + 'terrain.json', 'utf8')), bin = fs.readFileSync(data + 'terrain.bin');
  const pack = (h, bin) => { if (bin.length !== h.width * h.height * 2) throw new Error('terrain grid does not match its header'); return { south: h.south, west: h.west, north: h.north, east: h.east, width: h.width, height: h.height, b64: bin.toString('base64') }; };
  const T = pack(h, bin);
  if (fs.existsSync(data + 'terrain_outer.bin')) T.outer = pack(JSON.parse(fs.readFileSync(data + 'terrain_outer.json', 'utf8')), fs.readFileSync(data + 'terrain_outer.bin'));
  terrain = JSON.stringify(T);
}
// ---- mapped features, tree map, spectator areas
const rd = f => fs.existsSync(data + f) ? JSON.parse(fs.readFileSync(data + f, 'utf8')) : null;
const feats = (rd('features.json') || []).map(f => ({ k: f.kind[0], t: f.tags, p: f.pts }));
const vegSrc = rd('veg.json'), veg = vegSrc ? { step: vegSrc.step_m, half: vegSrc.half, stations: vegSrc.stations, course_m: vegSrc.course_m, trim: TRIM, b64: vegSrc.bits } : null;
// spectator areas named in the hill climb's guides, placed by landmark or by the elevation the guides give
const cumM = [0]; { const k = 111320 * Math.cos(course[0][0] * Math.PI / 180); for (let i = 1; i < course.length; i++) cumM.push(cumM[i - 1] + Math.hypot((course[i][1] - course[i - 1][1]) * k, (course[i][0] - course[i - 1][0]) * 111132)); }
const mileAtFt = ft => { for (let i = 1; i < course.length; i++) if (course[i][2] >= ft * 0.3048) return cumM[i] / MI; return null; };
const m9 = places.find(p => p.tags.highway === 'milestone' && p.tags.distance === '9 mi');
const spect = [[m9 ? m9.mile : null, '9 Mile'], [pick('Halfway Picnic Grounds'), 'Halfway Picnic Grounds'], [mileAtFt(10900), 'Ski Area'], [pick('Glen Cove', p => p.tags.place), 'Glen Cove'], [mileAtFt(11656), 'Cove Creek'], [pick("Devil's Playground", p => p.tags.amenity), "Devil's Playground"]].filter(a => a[0] != null).map(a => [+a[0].toFixed(3), a[1]]);
console.log('spectator areas:', spect.map(a => a[1] + ' ' + a[0]).join(', '), '| features', feats.length, '| tree map', veg ? veg.stations + ' stations' : 'none');
let s = '[\n'; for (let i = 0; i < course.length; i += 6) s += course.slice(i, i + 6).map(p => JSON.stringify(p)).join(',') + (i + 6 < course.length ? ',\n' : '\n'); s += ']';
t = t.replace('/*COURSE*/', () => s).replace('/*LANDMARKS*/', () => JSON.stringify(lm)).replace('/*TERRAIN*/', () => terrain).replace('/*FEATURES*/', () => JSON.stringify(feats)).replace('/*VEG*/', () => JSON.stringify(veg)).replace('/*SPECTATE*/', () => JSON.stringify(spect));
fs.writeFileSync(d + '/../index.html', t); console.log('bytes', t.length);
