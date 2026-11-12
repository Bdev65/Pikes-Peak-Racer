// Builds an approximated Pikes Peak hill climb course as [lat, lon, ele_m] points.
const fs = require('fs');
const MI = 1609.344, FT = 0.3048;
function rng(seed) { let s = seed >>> 0; return () => { s = (s + 0x6D2B79F5) >>> 0; let t = s; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

// landmark: [mile, feet, name]
const LM = [
  [0.0, 9390, 'Start Line'], [1.3, 9880, "Hansen's Corner"], [1.7, 9960, 'Horseshoe'],
  [2.3, 10130, "Engineer's Corner"], [2.9, 10330, 'Halfway Picnic Grounds'], [3.5, 10570, 'Brown Bush Corner'],
  [4.0, 10750, 'Big Spring'], [4.4, 10900, 'Blue Sky'], [4.8, 11000, '11 Mile Water Station'],
  [5.1, 11120, "Heitman's Hill"], [5.5, 11280, "Gilly's Corner"], [5.8, 11380, "Gayler's Straits"],
  [6.2, 11440, 'Glen Cove'], [6.6, 11570, "George's Corner"], [7.0, 11700, 'Cove Creek'],
  [7.3, 11850, 'Ragged Edge'], [7.7, 12000, 'Double Cut'], [8.0, 12100, 'Elk Park'],
  [8.3, 12250, "The W's"], [9.3, 12780, "Devil's Playground"], [9.9, 12900, 'Bottomless Pit'],
  [10.6, 13200, 'Upper Gravel Pit'], [11.0, 13380, 'Boulder Park'], [11.5, 13630, 'Cog Cut'],
  [12.0, 13900, 'Olympic'], [12.42, 14115, 'Summit']
];
// sections: miles, turns, style, target heading (deg, before final rotation)
const SEC = [
  { mi: 2.9, n: 26, st: 'fast', hd: 180 },
  { mi: 3.3, n: 40, st: 'med', hd: 150 },
  { mi: 2.1, n: 30, st: 'tech', hd: 200 },
  { mi: 1.0, n: 12, st: 'ws', hd: 170 },
  { mi: 1.3, n: 14, st: 'fast', hd: 190 },
  { mi: 1.82, n: 34, st: 'tech', hd: 165 }
];
function build(seed) {
  const R = rng(seed), prims = []; let hd = 180;
  for (const s of SEC) {
    const L = s.mi * MI, turns = [];
    for (let i = 0; i < s.n; i++) {
      let ang, rad, u = R();
      if (s.st === 'fast') { ang = 18 + R() * 55; rad = 70 + R() * 190; if (u < 0.12) { ang = 80 + R() * 50; rad = 35 + R() * 25; } }
      else if (s.st === 'med') { ang = 25 + R() * 70; rad = 40 + R() * 110; if (u < 0.12) { ang = 150 + R() * 25; rad = 14 + R() * 6; } }
      else if (s.st === 'tech') { ang = 30 + R() * 80; rad = 26 + R() * 70; if (u < 0.2) { ang = 150 + R() * 28; rad = 12 + R() * 6; } }
      else { if (i % 3 !== 1) { ang = 158 + R() * 14; rad = 12.5 + R() * 4; } else { ang = 12 + R() * 14; rad = 90 + R() * 60; } }
      turns.push({ ang, rad });
    }
    let A = turns.reduce((a, t) => a + t.ang * Math.PI / 180 * t.rad, 0);
    if (A > 0.78 * L) { const k = 0.78 * L / A; turns.forEach(t => t.rad = Math.max(11.5, t.rad * k)); A = turns.reduce((a, t) => a + t.ang * Math.PI / 180 * t.rad, 0); }
    const w = []; let ws = 0; for (let i = 0; i <= s.n; i++) { const v = 0.25 + R(); w.push(v); ws += v; }
    const SL = L - A; let lastDir = 1, hp = 0;
    for (let i = 0; i < s.n; i++) {
      prims.push({ len: SL * w[i] / ws, k: 0 });
      const t = turns[i]; let dir;
      const err = ((hd - s.hd + 540) % 360) - 180; // + means we point too far clockwise
      if (s.st === 'ws' && t.ang > 100) { dir = (hp++ % 2) ? 1 : -1; }
      else if (Math.abs(err) > 40) dir = err > 0 ? -1 : 1;
      else dir = R() < 0.7 ? -lastDir : lastDir;
      lastDir = dir; hd += dir * t.ang;
      prims.push({ len: t.ang * Math.PI / 180 * t.rad, k: dir / t.rad });
    }
    prims.push({ len: SL * w[s.n] / ws, k: 0 });
  }
  // integrate
  const pts = []; let x = 0, z = 0, h = Math.PI, dist = 0; const ds = 1; let acc = 0;
  pts.push([x, z, 0]);
  for (const p of prims) {
    let rem = p.len;
    while (rem > 0) { const st = Math.min(ds, rem); h += p.k * st; x += Math.sin(h) * st; z += Math.cos(h) * st; rem -= st; dist += st; acc += st; if (acc >= 10) { acc -= 10; pts.push([x, z, dist]); } }
  }
  pts.push([x, z, dist]);
  return pts;
}
function ok(pts) {
  for (let i = 0; i < pts.length; i += 2) for (let j = i + 12; j < pts.length; j += 2) {
    const dx = pts[i][0] - pts[j][0], dz = pts[i][1] - pts[j][1];
    if (dx * dx + dz * dz < 20 * 20) return false;
  } return true;
}
let pts, seed;
for (seed = 1; seed < 4000; seed++) { pts = build(seed); if (ok(pts)) break; }
console.error('seed', seed, 'points', pts.length, 'len mi', pts[pts.length - 1][2] / MI);
// rotate so start->finish bearing matches reality (summit lies ~184 deg from start)
const e = pts[pts.length - 1], cur = Math.atan2(e[0], e[1]), want = 184 * Math.PI / 180, rot = want - cur;
console.error('net displacement km', Math.hypot(e[0], e[1]) / 1000);
const lat0 = 38.9212, lon0 = -105.0370, mLat = 111132, mLon = 111320 * Math.cos(lat0 * Math.PI / 180);
function ele(d) { const mi = d / MI; for (let i = 1; i < LM.length; i++) if (mi <= LM[i][0] + 1e-9) { const t = (mi - LM[i - 1][0]) / (LM[i][0] - LM[i - 1][0]); return (LM[i - 1][1] + t * (LM[i][1] - LM[i - 1][1])) * FT; } return LM[LM.length - 1][1] * FT; }
const raw = pts.map(p => ele(p[2]));
const out = pts.map((p, i) => {
  let s = 0, n = 0; for (let j = Math.max(0, i - 12); j <= Math.min(pts.length - 1, i + 12); j++) { s += raw[j]; n++; }
  const xr = p[0] * Math.cos(rot) + p[1] * Math.sin(rot) * 1, zr = -p[0] * Math.sin(rot) + p[1] * Math.cos(rot);
  return [+(lat0 + zr / mLat).toFixed(6), +(lon0 + xr / mLon).toFixed(6), +(s / n).toFixed(1)];
});
const eb = out[out.length - 1]; console.error('end', eb, 'bearing check dLat', eb[0] - lat0, 'dLon', eb[1] - lon0);
fs.writeFileSync(__dirname + '/course.json', JSON.stringify(out));
fs.writeFileSync(__dirname + '/landmarks.json', JSON.stringify(LM.map(l => [+(l[0]).toFixed(2), l[2]])));
console.error('bytes', JSON.stringify(out).length);
