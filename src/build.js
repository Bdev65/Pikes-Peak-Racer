// Builds ../index.html from template.html and the fetched data in ../data (see tools/fetch_course.py).
const fs = require('fs'), d = __dirname, data = d + '/../data/';
const MI = 1609.344;
let t = fs.readFileSync(d + '/template.html', 'utf8');
const course = JSON.parse(fs.readFileSync(data + 'course.json', 'utf8'));
const places = fs.existsSync(data + 'places.json') ? JSON.parse(fs.readFileSync(data + 'places.json', 'utf8')) : [];

// ---- landmarks: only names whose position comes from the data
const lm = [];
const pick = (name, test) => { const c = places.filter(p => p.name === name && (!test || test(p))).sort((a, b) => a.off_m - b.off_m)[0]; return c ? c.mile : null; };
for (const [name, label, start, test] of [
  ['Halfway Picnic Grounds', 'Halfway Picnic Grounds', 1], ['Glen Cove', 'Glen Cove', 1, p => p.tags.place],
  ["Devil's Playground", "Devil's Playground", 1, p => p.tags.amenity], ['Little Pikes Peak', 'Little Pikes Peak', 0], ['Boulder Park', 'Boulder Park', 1]]) {
  const m = pick(name, test); if (m != null) lm.push([m, label, start]);
}
for (const p of places) if (p.tags.highway === 'milestone' && /^\d+ mi$/.test(p.tags.distance || '')) lm.push([p.mile, 'Mile ' + parseInt(p.tags.distance) + (p.name ? ' · ' + p.name : ''), 0]);
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
let s = '[\n'; for (let i = 0; i < course.length; i += 6) s += course.slice(i, i + 6).map(p => JSON.stringify(p)).join(',') + (i + 6 < course.length ? ',\n' : '\n'); s += ']';
t = t.replace('/*COURSE*/', () => s).replace('/*LANDMARKS*/', () => JSON.stringify(lm)).replace('/*TERRAIN*/', () => terrain);
fs.writeFileSync(d + '/../index.html', t); console.log('bytes', t.length);
