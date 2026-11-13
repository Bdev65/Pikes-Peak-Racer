#!/usr/bin/env python3
"""
Fetch the real Pikes Peak hill climb road and the terrain around it.

  Road:    OpenStreetMap (Overpass API)              (c) OpenStreetMap contributors, ODbL
  Terrain: USGS 3D Elevation Program (3DEP), ~10 m   public domain
           fallback: AWS Terrain Tiles (Terrarium)   mostly USGS 3DEP in the US

The race course is the last 12.42 mi (19.99 km) of the Pikes Peak Highway, ending at the summit,
so the script finds the highway in OpenStreetMap, routes along it from the summit back down,
and keeps the final 19.99 km.

Writes to data/:
  pikes-peak-course.gpx   the course with elevation (loadable in the game's menu)
  course.json             same points as [lat, lon, elevation_m]
  terrain.bin             elevation grid, uint16 little-endian, decimetres, rows north->south
  terrain.json            grid header (bounds, size, units)
  preview.png             shaded relief with the course drawn on it
  report.md               what was fetched, and checks against the published course figures

Run by .github/workflows/fetch-course.yml, or locally:  python tools/fetch_course.py
"""
import heapq, io, json, math, os, re, sys, time
from datetime import datetime, timezone

import numpy as np
import requests

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
COURSE_M = float(os.environ.get('COURSE_KM', '19.99')) * 1000
SUMMIT = (38.84053, -105.04428)                      # Pikes Peak summit
GLEN_COVE = (38.87554, -105.07298)                  # the Glen Cove locality in OpenStreetMap
SEARCH = (38.80, -105.13, 38.98, -104.95)            # south, west, north, east
PUBLISHED = {'start_ft': 9390, 'finish_ft': 14115, 'length_mi': 12.42, 'turns': 156}
UA = {'User-Agent': 'Pikes-Peak-Racer course builder (github.com/Bdev65/Pikes-Peak-Racer)'}
OVERPASS = ['https://overpass-api.de/api/interpreter',
            'https://overpass.kumi.systems/api/interpreter',
            'https://overpass.private.coffee/api/interpreter']
R_EARTH = 6371008.8
log = lambda *a: print(*a, flush=True)


def dist(a, b):
    la = math.radians((a[0] + b[0]) / 2)
    dx = math.radians(b[1] - a[1]) * math.cos(la) * R_EARTH
    dy = math.radians(b[0] - a[0]) * R_EARTH
    return math.hypot(dx, dy)


# ------------------------------------------------------------------ road
def overpass(q, what):
    last = None
    for url in OVERPASS:
        for attempt in range(2):
            try:
                log(f'Overpass ({what}): {url}')
                r = requests.post(url, data={'data': q}, headers=UA, timeout=180)
                r.raise_for_status()
                els = r.json()['elements']
                log(f'  {len(els)} elements')
                if els:
                    return els
            except Exception as ex:  # noqa: BLE001
                last = ex
                log(f'  failed: {ex}')
                time.sleep(10)
    raise RuntimeError(f'Could not reach any Overpass server: {last}')


def fetch_osm():
    s, w, n, e = SEARCH
    q = (f'[out:json][timeout:120];way["highway"]'
         f'["highway"!~"footway|path|steps|cycleway|bridleway|pedestrian|construction|proposed|corridor"]'
         f'({s},{w},{n},{e});out geom;')
    return [x for x in overpass(q, 'roads') if x['type'] == 'way' and 'geometry' in x]


def fetch_places(pts):
    """Named places and mileposts near the course, with their distance along it (for in-game landmark names)."""
    lats = [p[0] for p in pts]; lons = [p[1] for p in pts]
    s, w, n, e = min(lats) - 0.004, min(lons) - 0.005, max(lats) + 0.004, max(lons) + 0.005
    q = (f'[out:json][timeout:90];(node["name"]({s},{w},{n},{e});node["highway"="milestone"]({s},{w},{n},{e});'
         f'way["name"]["highway"!~"."]({s},{w},{n},{e});way["name"]["highway"~"path|footway|track|service"]({s},{w},{n},{e}););'
         f'out center tags;')
    els = overpass(q, 'places')
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + dist(a, b))
    P = np.array(pts)
    kx = 111320 * math.cos(math.radians(P[0, 0]))
    out = []
    for el in els:
        c = el if el['type'] == 'node' else el.get('center')
        if not c or 'lat' not in c:
            continue
        d = np.hypot((P[:, 0] - c['lat']) * 111132, (P[:, 1] - c['lon']) * kx)
        k = int(np.argmin(d))
        if d[k] > 300:
            continue
        tg = el.get('tags', {})
        out.append({'name': tg.get('name', ''), 'mile': round(cum[k] / 1609.344, 3), 'off_m': round(float(d[k])), 'lat': c['lat'], 'lon': c['lon'],
                    'type': el['type'], 'tags': {k2: v for k2, v in tg.items() if k2 in ('highway', 'place', 'natural', 'tourism', 'amenity', 'distance', 'ref', 'ele', 'railway', 'leisure', 'waterway')}})
    out.sort(key=lambda x: x['mile'])
    with open(os.path.join(OUT, 'places.json'), 'w') as f:
        json.dump(out, f, indent=0)
    log(f'  {len(out)} named places within 300 m of the course')


def course_from_ways(ways):
    """Route from the summit down the Pikes Peak Highway and keep the last COURSE_M metres."""
    named = lambda t: bool(re.search(r'pikes\s*peak', (t.get('name', '') + ' ' + t.get('ref', '') + ' ' + t.get('official_name', '')), re.I))
    pos, adj = {}, {}
    n_named = 0
    for wy in ways:
        tags = wy.get('tags', {})
        is_named = named(tags)
        n_named += is_named
        nodes = wy['nodes']
        for nid, g in zip(nodes, wy['geometry']):
            pos[nid] = (g['lat'], g['lon'])
        for a, b in zip(nodes, nodes[1:]):
            d = dist(pos[a], pos[b])
            c = d * (1.0 if is_named else 25.0)          # stay on the highway unless there is no other way
            adj.setdefault(a, []).append((b, c, d, is_named))
            adj.setdefault(b, []).append((a, c, d, is_named))
    log(f'  {n_named} ways named Pikes Peak; {len(pos)} nodes')
    if n_named == 0:
        raise RuntimeError('No ways named "Pikes Peak ..." found in the search area.')
    named_nodes = {a for a, lst in adj.items() if any(x[3] for x in lst)}
    top = min(named_nodes, key=lambda k: dist(pos[k], SUMMIT))
    log(f'  summit end of road: {pos[top]} ({dist(pos[top], SUMMIT):.0f} m from the summit marker)')
    # Dijkstra from the summit
    best = {top: 0.0}; length = {top: 0.0}; on_named = {top: 0.0}; prev = {}
    pq = [(0.0, top)]
    while pq:
        c, a = heapq.heappop(pq)
        if c > best.get(a, 1e18):
            continue
        for b, cost, d, isn in adj.get(a, []):
            nc = c + cost
            if nc < best.get(b, 1e18):
                best[b] = nc; length[b] = length[a] + d; on_named[b] = on_named[a] + (d if isn else 0); prev[b] = a
                heapq.heappush(pq, (nc, b))
    cands = [k for k in length if COURSE_M <= length[k] <= COURSE_M + 1500 and on_named[k] >= 0.97 * length[k]]
    if not cands:
        far = max(length.values())
        raise RuntimeError(f'Highway from the summit is only {far / 1000:.2f} km long in OpenStreetMap; need {COURSE_M / 1000:.2f} km.')
    start = min(cands, key=lambda k: length[k])
    path = [start]
    while path[-1] != top:
        path.append(prev[path[-1]])
    pts = [pos[k] for k in path]                       # start side -> summit
    # trim the bottom so the course is exactly COURSE_M long, measured back from the summit
    acc, out = 0.0, [pts[-1]]
    for i in range(len(pts) - 1, 0, -1):
        d = dist(pts[i], pts[i - 1])
        if acc + d >= COURSE_M:
            t = (COURSE_M - acc) / d
            out.append((pts[i][0] + t * (pts[i - 1][0] - pts[i][0]), pts[i][1] + t * (pts[i - 1][1] - pts[i][1])))
            break
        acc += d
        out.append(pts[i - 1])
    out.reverse()
    # densify so no gap is over 8 m (the game resamples anyway)
    dense = [out[0]]
    for a, b in zip(out, out[1:]):
        k = max(1, math.ceil(dist(a, b) / 8.0))
        for j in range(1, k + 1):
            dense.append((a[0] + (b[0] - a[0]) * j / k, a[1] + (b[1] - a[1]) * j / k))
    return dense


# ------------------------------------------------------------------ terrain
def bounds_for(pts, margin_m=900):
    lats = [p[0] for p in pts]; lons = [p[1] for p in pts]
    dlat = margin_m / 111132.0
    dlon = margin_m / (111320.0 * math.cos(math.radians(sum(lats) / len(lats))))
    return min(lats) - dlat, min(lons) - dlon, max(lats) + dlat, max(lons) + dlon


def fetch_usgs(b, res_m=10.0):
    """Ask the 3DEP ImageServer for a grid, then read back the extent it actually used
    (the server enlarges the requested box to keep its pixels square)."""
    s, w, n, e = b
    H = int(round((n - s) * 111132 / res_m))
    W = int(round(H * (e - w) / (n - s)))            # square pixels in degrees, so the box is not adjusted
    url = 'https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage'
    params = {'bbox': f'{w},{s},{e},{n}', 'bboxSR': 4326, 'imageSR': 4326, 'size': f'{W},{H}', 'format': 'tiff',
              'pixelType': 'F32', 'compression': 'None', 'noDataInterpretation': 'esriNoDataMatchAny',
              'interpolation': 'RSP_BilinearInterpolation', 'f': 'json'}
    import tifffile
    for attempt in range(3):
        try:
            log(f'USGS 3DEP: {W} x {H} grid (attempt {attempt + 1})')
            r = requests.get(url, params=params, headers=UA, timeout=300); r.raise_for_status()
            meta = r.json()
            if 'href' not in meta:
                raise RuntimeError('unexpected reply: ' + json.dumps(meta)[:200])
            ex = meta['extent']
            got = (ex['ymin'], ex['xmin'], ex['ymax'], ex['xmax'])
            log(f"  server extent {got}, {meta.get('width')} x {meta.get('height')}")
            r = requests.get(meta['href'], headers=UA, timeout=300); r.raise_for_status()
            if not r.content.startswith((b'II', b'MM')):
                raise RuntimeError('USGS did not return a TIFF: ' + r.text[:200])
            a = tifffile.imread(io.BytesIO(r.content)).astype(np.float64)
            if a.ndim > 2:
                a = a[..., 0]
            a[(a < -1000) | (a > 9000)] = np.nan
            if np.isnan(a).mean() > 0.01:
                raise RuntimeError(f'{np.isnan(a).mean() * 100:.1f}% of the grid has no data')
            return a, 'USGS 3D Elevation Program (3DEP), 1/3 arc-second, via the National Map ImageServer', got
        except Exception as ex:  # noqa: BLE001
            log(f'  failed: {ex}')
            time.sleep(15)
    return None, None, None


def check_dem(dem, b, src):
    """The summit is a surveyed 4,302 m (14,115 ft): a misplaced or bad grid shows up here."""
    z = float(sample(dem, b, [SUMMIT])[0])
    hi = float(np.nanmax(dem))
    log(f'  check: grid height at the summit marker {z:.0f} m, highest point in grid {hi:.0f} m (expect ~4302)')
    if abs(z - 4302) > 25 or abs(hi - 4302) > 25:
        raise RuntimeError(f'{src}: summit reads {z:.0f} m, highest point {hi:.0f} m; expected about 4302 m')


def fetch_terrarium(b, z=14):
    """AWS Terrain Tiles: PNG tiles, elevation = R*256 + G + B/256 - 32768 (metres)."""
    from PIL import Image
    s, w, n, e = b
    def tile(lat, lon):
        x = (lon + 180) / 360 * 2 ** z
        y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * 2 ** z
        return x, y
    x0, y0 = tile(n, w); x1, y1 = tile(s, e)
    tx0, ty0, tx1, ty1 = int(x0), int(y0), int(x1), int(y1)
    mosaic = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256))
    log(f'Terrain Tiles: {(tx1 - tx0 + 1) * (ty1 - ty0 + 1)} tiles at zoom {z}')
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            url = f'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{tx}/{ty}.png'
            r = requests.get(url, headers=UA, timeout=60); r.raise_for_status()
            im = np.asarray(Image.open(io.BytesIO(r.content)).convert('RGB')).astype(np.float64)
            mosaic[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = im[..., 0] * 256 + im[..., 1] + im[..., 2] / 256 - 32768
    # resample the Web-Mercator mosaic onto a regular lat/lon grid at ~10 m
    lat0 = (s + n) / 2
    W = int(round((e - w) * 111320 * math.cos(math.radians(lat0)) / 10)); H = int(round((n - s) * 111132 / 10))
    lats = n - (np.arange(H) + 0.5) / H * (n - s); lons = w + (np.arange(W) + 0.5) / W * (e - w)
    px = (lons + 180) / 360 * 2 ** z * 256 - tx0 * 256
    py = (1 - np.arcsinh(np.tan(np.radians(lats))) / np.pi) / 2 * 2 ** z * 256 - ty0 * 256
    PX, PY = np.meshgrid(px, py)
    return bilinear(mosaic, PX - 0.5, PY - 0.5), 'AWS Terrain Tiles (Terrarium), zoom 14 (mostly USGS 3DEP in the US)', b


def bilinear(a, fx, fy):
    fx = np.clip(fx, 0, a.shape[1] - 1.001); fy = np.clip(fy, 0, a.shape[0] - 1.001)
    x0 = np.floor(fx).astype(int); y0 = np.floor(fy).astype(int); u = fx - x0; v = fy - y0
    return (a[y0, x0] * (1 - u) * (1 - v) + a[y0, x0 + 1] * u * (1 - v) + a[y0 + 1, x0] * (1 - u) * v + a[y0 + 1, x0 + 1] * u * v)


def sample(dem, b, pts):
    s, w, n, e = b
    H, W = dem.shape
    lat = np.array([p[0] for p in pts]); lon = np.array([p[1] for p in pts])
    return bilinear(dem, (lon - w) / (e - w) * W - 0.5, (n - lat) / (n - s) * H - 0.5)


# ------------------------------------------------------------------ outputs
def count_turns(pts):
    """Rough corner count from the road shape, for comparison with the published 156."""
    xy = []
    lat0 = pts[0][0]
    for p in pts:
        xy.append((math.radians(p[1]) * math.cos(math.radians(lat0)) * R_EARTH, math.radians(p[0]) * R_EARTH))
    step = 10.0; res = [xy[0]]; acc = 0.0
    for a, b in zip(xy, xy[1:]):
        acc += math.hypot(b[0] - a[0], b[1] - a[1])
        if acc >= step:
            res.append(b); acc = 0.0
    hd = [math.atan2(b[0] - a[0], b[1] - a[1]) for a, b in zip(res, res[1:])]
    k = []
    for a, b in zip(hd, hd[1:]):
        d = (b - a + math.pi) % (2 * math.pi) - math.pi
        k.append(d / step)
    sm = np.convolve(np.array(k), np.ones(5) / 5, mode='same')
    turns, cur, sign, tot = 0, 0, 0, 0.0
    for v in sm:
        sg = 1 if v > 0.004 else -1 if v < -0.004 else 0
        if sg and sg == sign:
            tot += abs(v) * step
        else:
            if sign and tot > math.radians(25):
                turns += 1
            sign, tot = sg, abs(v) * step if sg else 0.0
    if sign and tot > math.radians(25):
        turns += 1
    return turns


def _near(pts):
    P = np.array(pts); kx = 111320 * math.cos(math.radians(P[0, 0]))
    return lambda la, lo: float(np.min(np.hypot((P[:, 0] - la) * 111132, (P[:, 1] - lo) * kx)))


def fetch_features(pts):
    """Buildings, parking areas and other roads near the course (for Glen Cove, pull-offs and spectator parking)."""
    lats = [p[0] for p in pts]; lons = [p[1] for p in pts]
    s, w, n, e = min(lats) - 0.004, min(lons) - 0.005, max(lats) + 0.004, max(lons) + 0.005
    q = (f'[out:json][timeout:120];(way["building"]({s},{w},{n},{e});way["amenity"="parking"]({s},{w},{n},{e});'
         f'way["highway"]["highway"!~"path|footway|steps|cycleway|bridleway|pedestrian|construction|proposed"]({s},{w},{n},{e}););out geom tags;')
    near = _near(pts); out = []
    for el in overpass(q, 'features'):
        g = el.get('geometry'); tg = el.get('tags', {})
        if not g:
            continue
        kind = 'building' if 'building' in tg else 'parking' if tg.get('amenity') == 'parking' else 'road'
        d = min(near(v['lat'], v['lon']) for v in g)
        if d > (150 if kind == 'road' else 260):
            continue
        out.append({'kind': kind, 'near_m': round(d), 'tags': {k: v for k, v in tg.items() if k in ('name', 'highway', 'building', 'surface', 'oneway', 'access', 'parking', 'service', 'lanes', 'tourism', 'amenity')},
                    'pts': [[round(v['lat'], 6), round(v['lon'], 6)] for v in g]})
    with open(os.path.join(OUT, 'features.json'), 'w') as f:
        json.dump(out, f, separators=(',', ':'))
    log('  ' + ', '.join(f"{sum(1 for o in out if o['kind'] == k)} {k}s" for k in ('building', 'parking', 'road')))


def naip(b, W, H):
    """Aerial photo (USDA NAIP via the USGS image service) as an array H x W x bands, plus the extent returned."""
    import tifffile
    s, w, n, e = b; last = None
    for svc in ('USGSNAIPPlus', 'USGSNAIPImagery'):
        url = f'https://imagery.nationalmap.gov/arcgis/rest/services/{svc}/ImageServer/exportImage'
        params = {'bbox': f'{w},{s},{e},{n}', 'bboxSR': 4326, 'imageSR': 4326, 'size': f'{W},{H}', 'format': 'tiff', 'pixelType': 'U8',
                  'compression': 'LZW', 'interpolation': 'RSP_BilinearInterpolation', 'f': 'json'}
        try:
            log(f'NAIP {svc}: {W} x {H}')
            r = requests.get(url, params=params, headers=UA, timeout=300); r.raise_for_status(); meta = r.json()
            if 'href' not in meta:
                raise RuntimeError(json.dumps(meta)[:300])
            ex = meta['extent']; r = requests.get(meta['href'], headers=UA, timeout=300); r.raise_for_status()
            a = tifffile.imread(io.BytesIO(r.content))
            if a.ndim == 2:
                a = a[..., None]
            if a.shape[0] < 8 and a.shape[2] > 8:
                a = np.moveaxis(a, 0, -1)
            log(f'  got {a.shape}, band means {[round(float(a[..., k].mean()), 1) for k in range(a.shape[2])]}')
            if a[..., :3].mean() < 3:
                raise RuntimeError('image is blank')
            return a.astype(np.float32), (ex['ymin'], ex['xmin'], ex['ymax'], ex['xmax'])
        except Exception as ex:  # noqa: BLE001
            last = ex; log(f'  failed: {ex}')
    raise RuntimeError(f'no aerial imagery: {last}')


def fetch_veg(pts):
    """Where the trees are: a tree / open-ground map in road coordinates (every 6 m along, 150 m to each side), from aerial photos."""
    from PIL import Image
    b = bounds_for(pts, 230); s, w, n, e = b
    H = min(3900, int(round((n - s) * 111132 / 3.0))); W = int(round(H * (e - w) / (n - s)))
    a, (s, w, n, e) = naip(b, W, H); H, W = a.shape[:2]
    R, G, B = a[..., 0], a[..., 1], a[..., 2]; bright = (R + G + B) / 3
    if a.shape[2] >= 4:
        N = a[..., 3]; ndvi = (N - R) / (N + R + 1); tree = (ndvi > VEG_NDVI) & (bright < VEG_DARK)
    else:
        ndvi = (2 * G - R - B) / (R + G + B + 1); tree = (ndvi > 0.03) & (bright < VEG_DARK)
    pad = np.pad(tree.astype(np.float32), 1, mode='edge'); frac = sum(pad[i:i + H, j:j + W] for i in range(3) for j in range(3)) / 9
    # stations every 6 m along the course
    cum = [0.0]
    for p, q in zip(pts, pts[1:]):
        cum.append(cum[-1] + dist(p, q))
    P = np.array(pts); st = np.arange(0, cum[-1], 6.0); la = np.interp(st, cum, P[:, 0]); lo = np.interp(st, cum, P[:, 1])
    kx = 111320 * math.cos(math.radians(P[0, 0])); x = lo * kx; y = la * 111132
    tx = np.gradient(x); ty = np.gradient(y); L = np.hypot(tx, ty) + 1e-9; rx = ty / L; ry = -tx / L       # unit vector to the right of travel
    offs = (np.arange(51) - 25) * 6.0
    X = x[:, None] + rx[:, None] * offs[None, :]; Y = y[:, None] + ry[:, None] * offs[None, :]
    px = np.clip(((X / kx - w) / (e - w) * W).astype(int), 0, W - 1); py = np.clip(((n - Y / 111132) / (n - s) * H).astype(int), 0, H - 1)
    m = frac[py, px] > 0.5
    info = {'step_m': 6, 'side_step_m': 6, 'half': 25, 'stations': int(len(st)), 'course_m': round(cum[-1], 1), 'tree_share': round(float(m.mean()), 3),
            'bits': __import__('base64').b64encode(np.packbits(m.astype(np.uint8), axis=None).tobytes()).decode()}
    with open(os.path.join(OUT, 'veg.json'), 'w') as f:
        json.dump(info, f)
    log(f'  tree map: {len(st)} stations, {m.mean() * 100:.0f}% trees')
    # preview: photo and tree map side by side for three places, so the thresholds can be checked by eye
    tiles = []
    for frac_along in (0.03, 0.25, 0.47):
        k = int(frac_along * len(st)); cx = int((lo[k] - w) / (e - w) * W); cy = int((n - la[k]) / (n - s) * H); r = 150
        x0 = max(0, min(W - 2 * r, cx - r)); y0 = max(0, min(H - 2 * r, cy - r))
        rgb = np.clip(a[y0:y0 + 2 * r, x0:x0 + 2 * r, :3], 0, 255).astype(np.uint8); ov = rgb.copy(); tm = tree[y0:y0 + 2 * r, x0:x0 + 2 * r]
        ov[tm] = (0.4 * ov[tm] + 0.6 * np.array([255, 0, 200])).astype(np.uint8); tiles.append(np.concatenate([rgb, ov], axis=1))
    Image.fromarray(np.concatenate(tiles, axis=0)).resize((1200, 1800), Image.NEAREST).save(os.path.join(OUT, 'veg_preview.png'))


def fetch_photo(center, half_m, name):
    from PIL import Image
    dlat = half_m / 111132; dlon = half_m / (111320 * math.cos(math.radians(center[0])))
    b = (center[0] - dlat, center[1] - dlon, center[0] + dlat, center[1] + dlon)
    a, got = naip(b, 1100, int(1100 * dlat / dlon))
    Image.fromarray(np.clip(a[..., :3], 0, 255).astype(np.uint8)).save(os.path.join(OUT, name + '.jpg'), quality=88)
    json.dump({'south': got[0], 'west': got[1], 'north': got[2], 'east': got[3]}, open(os.path.join(OUT, name + '.json'), 'w'))


VEG_NDVI, VEG_DARK = 0.15, 105


def write_grid(dem, b, cell_m, name, src):
    """Save an elevation grid for the game: block-averaged to about cell_m, uint16 decimetres."""
    s, w, n, e = b
    H, W = dem.shape
    f = max(1, int(round(cell_m / ((n - s) * 111132 / H))))
    g = np.nanmean(dem[:H // f * f, :W // f * f].reshape(H // f, f, W // f, f), axis=(1, 3))
    g = np.nan_to_num(g, nan=float(np.nanmin(dem)))
    q = np.clip(np.round(g * 10), 0, 65535).astype('<u2')
    q.tofile(os.path.join(OUT, name + '.bin'))
    hdr = {'south': n - (n - s) * (H // f * f) / H, 'west': w, 'north': n, 'east': w + (e - w) * (W // f * f) / W,
           'width': int(q.shape[1]), 'height': int(q.shape[0]), 'format': 'uint16 little-endian, row-major, first row is the north edge',
           'units': 'decimetres above sea level', 'cell_m': round((n - s) * 111132 / H * f, 2), 'source': src}
    with open(os.path.join(OUT, name + '.json'), 'w') as fh:
        json.dump(hdr, fh, indent=1)
    log(f'  {name}: {q.shape[1]} x {q.shape[0]} cells of {hdr["cell_m"]} m')


def write_outputs(pts, ele, dem, b, src_dem):
    os.makedirs(OUT, exist_ok=True)
    # light smoothing of road elevation: a 10 m grid mixes the road with the slope beside it
    e = np.array(ele, dtype=float)
    k = 7
    pad = np.pad(e, (k, k), mode='edge')
    e_s = np.convolve(pad, np.ones(2 * k + 1) / (2 * k + 1), mode='same')[k:-k]
    course = [[round(p[0], 6), round(p[1], 6), round(float(z), 1)] for p, z in zip(pts, e_s)]
    with open(os.path.join(OUT, 'course.json'), 'w') as f:
        json.dump(course, f, separators=(',', ':'))
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    with open(os.path.join(OUT, 'pikes-peak-course.gpx'), 'w') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="Pikes-Peak-Racer tools/fetch_course.py" '
                'xmlns="http://www.topografix.com/GPX/1/1">\n'
                f'<metadata><name>Pikes Peak International Hill Climb course</name><time>{now}</time>'
                '<copyright author="OpenStreetMap contributors"><license>https://opendatacommons.org/licenses/odbl/</license></copyright></metadata>\n'
                '<trk><name>Start line to summit</name><trkseg>\n')
        for c in course:
            f.write(f'<trkpt lat="{c[0]}" lon="{c[1]}"><ele>{c[2]}</ele></trkpt>\n')
        f.write('</trkseg></trk>\n</gpx>\n')
    # terrain grid at ~20 m for the game (the 10 m source is kept only for sampling the road)
    s, w, n, e2 = b
    H, W = dem.shape
    f2 = 2
    g = dem[:H // f2 * f2, :W // f2 * f2].reshape(H // f2, f2, W // f2, f2).mean(axis=(1, 3))
    g = np.nan_to_num(g, nan=float(np.nanmin(dem)))
    q = np.clip(np.round(g * 10), 0, 65535).astype('<u2')
    q.tofile(os.path.join(OUT, 'terrain.bin'))
    hdr = {'south': s, 'west': w, 'north': n, 'east': w + (e2 - w) * (W // f2 * f2) / W,
           'width': int(q.shape[1]), 'height': int(q.shape[0]), 'format': 'uint16 little-endian, row-major, first row is the north edge',
           'units': 'decimetres above sea level', 'cell_m': round((n - s) * 111132 / H * f2, 2), 'source': src_dem}
    hdr['south'] = n - (n - s) * (H // f2 * f2) / H
    with open(os.path.join(OUT, 'terrain.json'), 'w') as f:
        json.dump(hdr, f, indent=1)
    # preview: shaded relief + course
    from PIL import Image, ImageDraw
    gy, gx = np.gradient(g, hdr['cell_m'])
    sl = np.pi / 2 - np.arctan(np.hypot(gx, gy)); asp = np.arctan2(-gx, gy)
    az, alt = math.radians(315), math.radians(45)
    shade = np.clip(np.sin(alt) * np.sin(sl) + np.cos(alt) * np.cos(sl) * np.cos(az - math.pi / 2 - asp), 0, 1)
    tint = np.clip((g - np.nanmin(g)) / (np.nanmax(g) - np.nanmin(g) + 1), 0, 1)
    rgb = np.stack([90 + 120 * tint, 110 + 90 * tint, 80 + 110 * tint], -1) * (0.35 + 0.75 * shade[..., None])
    im = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
    r = 1000 / max(im.size)
    im = im.resize((int(im.size[0] * r), int(im.size[1] * r)), Image.LANCZOS)
    dr = ImageDraw.Draw(im)
    PW, PH = im.size
    xy = [((p[1] - w) / (hdr['east'] - w) * PW, (n - p[0]) / (n - hdr['south']) * PH) for p in pts]
    dr.line(xy, fill=(20, 20, 20), width=5); dr.line(xy, fill=(244, 160, 32), width=3)
    for (x, y), col in ((xy[0], (60, 200, 90)), (xy[-1], (230, 60, 50))):
        dr.ellipse((x - 7, y - 7, x + 7, y + 7), fill=col, outline=(0, 0, 0), width=2)
    im.save(os.path.join(OUT, 'preview.png'))
    return course


def main():
    log('== Road from OpenStreetMap')
    pts = course_from_ways(fetch_osm())
    length = sum(dist(a, b) for a, b in zip(pts, pts[1:]))
    log(f'  course: {len(pts)} points, {length / 1609.344:.2f} mi')
    b = bounds_for(pts)
    log('== Terrain')
    dem, src, gb = fetch_usgs(b)
    try:
        if dem is None:
            raise RuntimeError('USGS unavailable')
        check_dem(dem, gb, src)
    except Exception as ex:  # noqa: BLE001
        log(f'  {ex}; trying Terrain Tiles')
        dem, src, gb = fetch_terrarium(b)
        check_dem(dem, gb, src)
    b = gb
    ele = sample(dem, b, pts)
    course = write_outputs(pts, ele, dem, b, src)
    try:
        log('== Wider terrain for the distant view (3 km around the course, ~60 m cells)')
        ob = bounds_for(pts, 3000)
        odem, osrc, ogb = fetch_usgs(ob, 30.0)
        if odem is None:
            odem, osrc, ogb = fetch_terrarium(ob, 12)
        write_grid(odem, ogb, 60.0, 'terrain_outer', osrc)
    except Exception as ex:  # noqa: BLE001
        log(f'  wider terrain skipped: {ex}')
    for label, fn in (('Buildings, parking and side roads', lambda: fetch_features(pts)), ('Tree map from aerial photos', lambda: fetch_veg(pts)),
                      ('Aerial photo of Glen Cove', lambda: fetch_photo(GLEN_COVE, 260, 'glen_cove'))):
        try:
            log('== ' + label)
            fn()
        except Exception as ex:  # noqa: BLE001
            log(f'  skipped: {ex}')
    try:
        log('== Places')
        fetch_places(pts)
    except Exception as ex:  # noqa: BLE001
        log(f'  places skipped: {ex}')
    z0, z1 = course[0][2], course[-1][2]
    turns = count_turns(pts)
    rows = [
        ('Length', f'{length / 1609.344:.2f} mi', f"{PUBLISHED['length_mi']} mi"),
        ('Start elevation', f'{z0 / 0.3048:,.0f} ft', f"{PUBLISHED['start_ft']:,} ft"),
        ('Finish elevation', f'{z1 / 0.3048:,.0f} ft', f"{PUBLISHED['finish_ft']:,} ft (summit)"),
        ('Climb', f'{(z1 - z0) / 0.3048:,.0f} ft', f"{PUBLISHED['finish_ft'] - PUBLISHED['start_ft']:,} ft"),
        ('Corners (rough count)', str(turns), f"{PUBLISHED['turns']} (official count, includes gentle bends)"),
    ]
    rep = ['# Course data report', '', f'Fetched {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC.', '',
           '| | From the data | Published |', '|---|---|---|'] + [f'| {a} | {b_} | {c} |' for a, b_, c in rows] + [
           '', f'- Road: OpenStreetMap, {len(pts)} points (© OpenStreetMap contributors, ODbL)',
           f'- Terrain: {src}', f"- Grid saved for the game: {json.load(open(os.path.join(OUT, 'terrain.json')))['width']} x "
           f"{json.load(open(os.path.join(OUT, 'terrain.json')))['height']} cells", '', '![Course preview](preview.png)', '']
    open(os.path.join(OUT, 'report.md'), 'w').write('\n'.join(rep))
    log('\n'.join(rep))


if __name__ == '__main__':
    try:
        main()
    except Exception as ex:  # noqa: BLE001
        log(f'ERROR: {ex}')
        os.makedirs(OUT, exist_ok=True)
        open(os.path.join(OUT, 'report.md'), 'w').write(f'# Course data report\n\nThe last run failed:\n\n    {ex}\n')
        sys.exit(1)
