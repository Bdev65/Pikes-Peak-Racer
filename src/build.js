const fs = require('fs'), d = __dirname;
let t = fs.readFileSync(d + '/template.html', 'utf8');
const c = JSON.parse(fs.readFileSync(d + '/course.json', 'utf8'));
let s = '[\n'; for (let i = 0; i < c.length; i += 6) s += c.slice(i, i + 6).map(p => JSON.stringify(p)).join(',') + (i + 6 < c.length ? ',\n' : '\n'); s += ']';
t = t.replace('/*COURSE*/', () => s).replace('/*LANDMARKS*/', () => fs.readFileSync(d + '/landmarks.json', 'utf8'));
fs.writeFileSync(d + '/../index.html', t); console.log('bytes', t.length);
