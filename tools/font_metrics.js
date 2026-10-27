// SPDX-License-Identifier: GPL-3.0-or-later
// Read advance widths of printable ASCII from TTF files and write src/klipmi/canvas/metrics.py.
//
//   node tools/font_metrics.js
//
// Needs the Inter download (hmi/plus4-canvas/assets/inter/extras/ttf, see hmi/plus4-canvas/README.md).
const fs = require("fs");
const path = require("path");

const dir = path.join(__dirname, "..", "hmi", "plus4-canvas", "assets", "inter", "extras", "ttf");
const out = path.join(__dirname, "..", "src", "klipmi", "canvas", "metrics.py");

function advances(file) {
  const b = fs.readFileSync(file);
  const tables = {};
  for (let i = 0; i < b.readUInt16BE(4); i++) {
    const o = 12 + i * 16;
    tables[b.toString("latin1", o, o + 4)] = b.readUInt32BE(o + 8);
  }
  const upm = b.readUInt16BE(tables.head + 18);
  const nHM = b.readUInt16BE(tables.hhea + 34);
  // cmap: find a format 4 subtable for the BMP (platform 3, encoding 1) or Unicode (0)
  const cm = tables.cmap, n = b.readUInt16BE(cm + 2);
  let sub = -1;
  for (let i = 0; i < n; i++) {
    const plat = b.readUInt16BE(cm + 4 + i * 8), enc = b.readUInt16BE(cm + 6 + i * 8);
    const off = cm + b.readUInt32BE(cm + 8 + i * 8);
    if (b.readUInt16BE(off) === 4 && (plat === 3 && enc === 1 || plat === 0)) { sub = off; break; }
  }
  if (sub < 0) throw new Error("no format 4 cmap in " + file);
  const segX2 = b.readUInt16BE(sub + 6), ends = sub + 14, starts = ends + segX2 + 2;
  const deltas = starts + segX2, ranges = deltas + segX2;
  const glyph = (cp) => {
    for (let s = 0; s < segX2 / 2; s++) {
      if (cp <= b.readUInt16BE(ends + 2 * s)) {
        const st = b.readUInt16BE(starts + 2 * s);
        if (cp < st) return 0;
        const ro = b.readUInt16BE(ranges + 2 * s), dl = b.readUInt16BE(deltas + 2 * s);
        if (ro === 0) return (cp + dl) & 0xffff;
        const g = b.readUInt16BE(ranges + 2 * s + ro + 2 * (cp - st));
        return g === 0 ? 0 : (g + dl) & 0xffff;
      }
    }
    return 0;
  };
  const adv = {};
  for (let cp = 32; cp < 127; cp++) {
    const g = glyph(cp);
    const idx = Math.min(g, nHM - 1);
    adv[cp] = b.readUInt16BE(tables.hmtx + idx * 4);
  }
  return { upm, adv };
}

const lines = ['# SPDX-License-Identifier: GPL-3.0-or-later',
  '"""Advance widths (font units) of ASCII 32-126 in Inter, from tools/font_metrics.js. Do not edit."""', ''];
for (const [name, file] of [["REGULAR", "Inter-Regular.ttf"], ["LIGHT", "Inter-Light.ttf"], ["SEMIBOLD", "Inter-SemiBold.ttf"]]) {
  const { upm, adv } = advances(path.join(dir, file));
  lines.push(`UPM_${name} = ${upm}`);
  lines.push(`ADV_${name} = [`);
  const vals = [];
  for (let cp = 32; cp < 127; cp++) vals.push(adv[cp]);
  for (let i = 0; i < vals.length; i += 12) lines.push("    " + vals.slice(i, i + 12).join(", ") + ",");
  lines.push("]", "");
}
fs.writeFileSync(out, lines.join("\n"));
console.log("wrote", out);
