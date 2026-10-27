// SPDX-License-Identifier: GPL-3.0-or-later
// Render the HMI picture assets (icon strips, anti-aliased corner atlas) to PNG.
// No dependencies: headless Chrome draws on a canvas, we pull the PNGs out of --dump-dom.
//
//   node tools/hmi_assets.js [outdir]      (default hmi/plus4-canvas/assets/pics)
//
// Icons are 24-unit stroke drawings (our own, drawn for this UI). Pictures have no alpha, so every icon
// strip is baked for one (ink, backdrop) pair and every corner sheet for one (fill, backdrop) pair.
// Output: PNGs plus pics.json, whose "order" is the picture id order in the HMI editor.
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const root = path.join(__dirname, "..", "hmi", "plus4-canvas", "assets");
const outDir = process.argv[2] || path.join(root, "pics");
const CHROME = process.env.CHROME || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";

// Mirrors Theme in src/klipmi/canvas/gfx.py.
const THEME = {
  bg: [14, 16, 20], surface: [30, 34, 41], surface2: [44, 49, 58], border: [58, 64, 75],
  text: [236, 239, 244], muted: [140, 148, 160], accent: [0, 180, 235], ok: [64, 200, 120],
  err_dim: [110, 32, 36], err_ink: [255, 154, 154],
};

// name -> SVG body in a 24x24 box, stroked
const ICONS = {
  home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9v12h14V9"/><path d="M10 21v-6h4v6"/>',
  move: '<path d="M12 3v18M3 12h18"/><path d="m9 6 3-3 3 3M9 18l3 3 3-3M6 9l-3 3 3 3M18 9l3 3-3 3"/>',
  temp: '<path d="M14 14.8V4.5a2 2 0 0 0-4 0v10.3a4 4 0 1 0 4 0z"/><path d="M12 9v8"/>',
  fan: '<circle cx="12" cy="12" r="1.5"/><path d="M12 10.5C9 8 9.5 3.5 12 3c3 .5 2.5 5 0 7.5zM13.5 12c2.5-3 7-2.5 7.5 0-.5 3-5 2.5-7.5 0zM12 13.5c3 2.5 2.5 7 0 7.5-3-.5-2.5-5 0-7.5zM10.5 12C8 15 3.5 14.5 3 12c.5-3 5-2.5 7.5 0z"/>',
  spool: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="1"/>',
  files: '<path d="M14 3H6.5A1.5 1.5 0 0 0 5 4.5v15A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V8z"/><path d="M14 3v5h5M8.5 13h7M8.5 17h5"/>',
  target: '<circle cx="12" cy="12" r="7.5"/><circle cx="12" cy="12" r="2.5"/><path d="M12 1.5v4M12 18.5v4M1.5 12h4M18.5 12h4"/>',
  sys: '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
  stop: '<path d="M8.3 2.5h7.4l5.8 5.8v7.4l-5.8 5.8H8.3l-5.8-5.8V8.3z"/><path d="M12 7.5v5.5M12 16.5v.5"/>',
  nozzle: '<path d="M6 3h12v5H6zM8 8h8l-2.5 6h-3zM12 14v2.5M12 19.5v.5"/>',
  bed: '<path d="M2.5 17h19M5 17v3M19 17v3"/><path d="M7 13c1.2-1.5-1.2-3 0-4.5S7 5 7 5M12 13c1.2-1.5-1.2-3 0-4.5S12 5 12 5M17 13c1.2-1.5-1.2-3 0-4.5S17 5 17 5"/>',
  chamber: '<rect x="3" y="3" width="18" height="18" rx="2.5"/><path d="M3 8h18"/><path d="M9 17.5c1-1.2-1-2.3 0-3.5M15 17.5c1-1.2-1-2.3 0-3.5"/>',
  drop: '<path d="M12 3s-6.5 7-6.5 11.5a6.5 6.5 0 0 0 13 0C18.5 10 12 3 12 3z"/>',
  light: '<path d="M9 18h6M10 21.5h4"/><path d="M12 2.5a6.5 6.5 0 0 0-4 11.6c.7.6 1 1.4 1 2.4v.5h6v-.5c0-1 .3-1.8 1-2.4a6.5 6.5 0 0 0-4-11.6z"/>',
  power: '<path d="M12 3v8"/><path d="M6.6 6.6a7.5 7.5 0 1 0 10.8 0"/>',
  wifi: '<path d="M2.5 9a14 14 0 0 1 19 0M5.5 12.5a9.5 9.5 0 0 1 13 0M8.8 16a4.8 4.8 0 0 1 6.4 0"/><path d="M12 19.5v.5"/>',
  play: '<path d="M7 4.5v15l12-7.5z"/>',
  pause: '<path d="M8 5v14M16 5v14"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
  hour: '<path d="M6 3h12M6 21h12M7 3c0 5 10 6 10 9s-10 4-10 9M17 3c0 5-10 6-10 9s10 4 10 9"/>',
  flag: '<path d="M5 21V4M5 4h12l-2.5 4.5L17 13H5"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
  gauge: '<path d="M3.5 17a8.5 8.5 0 1 1 17 0"/><path d="M12 17l4-5.5"/>',
  flow: '<path d="M3 8c3-3 6 3 9 0s6 3 9 0M3 16c3-3 6 3 9 0s6 3 9 0"/>',
  z: '<path d="M7 6h10L7 18h10"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  minus: '<path d="M5 12h14"/>',
  reset: '<path d="M4 12a8 8 0 1 0 2.3-5.7"/><path d="M4 4v5h5"/>',
  cube: '<path d="m12 3 8 4.5v9L12 21l-8-4.5v-9z"/><path d="m4 7.5 8 4.5 8-4.5M12 12v9"/>',
  check: '<path d="m4.5 12.5 5 5 10-11"/>',
  del: '<path d="M9 5h11v14H9l-6-7z"/><path d="M12.5 9.5l5 5M17.5 9.5l-5 5"/>',
  up: '<path d="m5 15 7-7 7 7"/>',
  down: '<path d="m5 9 7 7 7-7"/>',
  left: '<path d="m15 5-7 7 7 7"/>',
  right: '<path d="m9 5 7 7-7 7"/>',
  level: '<path d="M3 18h18M5 14l14-4M7 14v-2M17 11V9"/>',
  extrude: '<path d="M12 3v12M7 10l5 5 5-5M5 20h14"/>',
  retract: '<path d="M12 15V3M7 8l5-5 5 5M5 20h14"/>',
  arrow: '<path d="M4 12h15M13 6l6 6-6 6"/>',
  snow: '<path d="M12 2v20M3.3 7l17.4 10M3.3 17 20.7 7"/><path d="m9 4 3 2 3-2M9 20l3-2 3 2"/>',
  part: '<path d="M6 3h12v5H6zM8 8h8l-2.5 6h-3z"/><path d="M3 19c2-1.5 4-1.5 6 0s4 1.5 6 0 4-1.5 6 0"/>',
  side: '<rect x="3" y="4" width="8" height="16" rx="2"/><path d="M14 8c2 0 2 2 4 2s2-2 4-2M14 14c2 0 2 2 4 2s2-2 4-2"/>',
  exhaust: '<path d="M4 20V9l8-5 8 5v11"/><path d="M9 20v-5h6v5M12 4V1.5"/>',
  eject: '<path d="M5 19h14M12 4.5 19 14H5z"/>',
  refresh: '<path d="M20 12a8 8 0 1 1-2.3-5.7"/><path d="M20 4v5h-5"/>',
  wrench: '<path d="M14.5 5.5a4.5 4.5 0 0 0 5.6 5.6L12 19.2a2 2 0 0 1-3-3L17.1 8"/><path d="M14.5 5.5 17 3l4 4-2.5 2.5"/>',
  bypass: '<path d="M4 4v6a4 4 0 0 0 4 4h12M16 10l4 4-4 4"/>',
  guard: '<path d="M12 3 4.5 6v6c0 4.5 3.2 7.8 7.5 9 4.3-1.2 7.5-4.5 7.5-9V6z"/>',
  back: '<path d="M19 12H5M11 6l-6 6 6 6"/>',
  sort: '<path d="M7 4v16M3.5 16.5 7 20l3.5-3.5M17 20V4M13.5 7.5 17 4l3.5 3.5"/>',
  folder: '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5H9l2 2.5h8.5A1.5 1.5 0 0 1 21 9v9.5a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5z"/>',
  trash: '<path d="M4 7h16M9.5 7V4h5v3M6 7l1 13.5h10L18 7"/>',
  weight: '<path d="M6.5 8h11l3 12h-17z"/><circle cx="12" cy="5.5" r="2.5"/>',
  cal: '<rect x="3.5" y="5" width="17" height="15.5" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
  wave: '<path d="M2 12h3l2-6 3 12 3-14 3 12 2-4h4"/>',
  pid: '<path d="M3 19h18"/><path d="M3 17c3 0 3-12 6-12s3 8 6 8 3-2 6-2"/>',
  screw: '<circle cx="12" cy="12" r="8"/><path d="M8.5 8.5l7 7M15.5 8.5l-7 7"/>',
  bolt: '<path d="M13 2.5 4.5 14H11l-1 7.5L18.5 10H12z"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
  moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  sound: '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/><path d="M15.5 9a4.5 4.5 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11"/>',
  reboot: '<path d="M4 12a8 8 0 1 0 2.3-5.7"/><path d="M4 4v5h5M12 8v4"/>',
  warn: '<path d="M12 3.5 2.5 20h19z"/><path d="M12 10v4.5M12 17.5v.5"/>',
  lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7.5a4 4 0 0 1 8 0V11"/>',
};
const PER_ROW = 25;
const SIZES = [24, 32];
// (ink, backdrop) pairs an icon strip is baked for; order = picture order within one size
const INKS = [
  ["muted", "bg"], ["text", "bg"], ["accent", "surface"], ["muted", "surface"], ["text", "surface"],
  ["ok", "surface"], ["muted", "surface2"], ["text", "surface2"], ["bg", "accent"], ["err_ink", "err_dim"],
];
const RADII = [4, 6, 8, 10, 12, 16, 20, 24];
// (fill, backdrop) corner sheets, laid out 8 per row in one atlas picture
const CORNER_PAIRS = [
  ["surface", "bg"], ["surface2", "surface"], ["surface2", "bg"], ["accent", "bg"], ["accent", "surface"],
  ["accent", "surface2"], ["err_dim", "bg"], ["err_dim", "surface"], ["border", "surface"], ["surface", "border"],
  ["border", "bg"], ["bg", "border"], ["bg", "surface"], ["surface2", "accent"], ["text", "bg"], ["text", "surface"],
  ["surface2", "text"], ["accent", "text"], ["err_dim", "text"], ["surface", "text"], ["bg", "text"], ["text", "accent"],
  ["muted", "surface2"], ["accent", "err_dim"],
];
const SHEET_W = 4 * Math.max(...RADII), SHEET_H = RADII.reduce((a, b) => a + b, 0), SHEETS_PER_ROW = 8;

const names = Object.keys(ICONS);
const svgs = names.map(n => {
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="96" height="96" fill="none" stroke="#fff" ' +
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + ICONS[n] + "</svg>";
  return "data:image/svg+xml;base64," + Buffer.from(svg).toString("base64");
});

const job = { THEME, svgs, PER_ROW, SIZES, INKS, RADII, CORNER_PAIRS, SHEET_W, SHEET_H, SHEETS_PER_ROW };
const html = `<!doctype html><meta charset=utf-8><pre id=out>pending</pre><script>
const J = ${JSON.stringify(job)};
const css = c => "rgb(" + c.join(",") + ")";
const load = src => new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = src; });
(async () => {
  const out = {};
  const imgs = await Promise.all(J.svgs.map(load));
  const rows = Math.ceil(imgs.length / J.PER_ROW);
  for (const s of J.SIZES) for (const [ink, bg] of J.INKS) {
    // draw white glyphs once, then tint: ink where the glyph is, backdrop elsewhere (blended by coverage)
    const c = document.createElement("canvas"); c.width = s * J.PER_ROW; c.height = s * rows;
    const x = c.getContext("2d"); x.imageSmoothingQuality = "high";
    imgs.forEach((im, k) => x.drawImage(im, (k % J.PER_ROW) * s, Math.floor(k / J.PER_ROW) * s, s, s));
    const d = x.getImageData(0, 0, c.width, c.height), p = d.data, a = J.THEME[ink], b = J.THEME[bg];
    for (let i = 0; i < p.length; i += 4) {
      const t = p[i + 3] / 255;
      for (let ch = 0; ch < 3; ch++) p[i + ch] = Math.round(b[ch] + (a[ch] - b[ch]) * t);
      p[i + 3] = 255;
    }
    x.putImageData(d, 0, 0);
    out["ic" + s + "_" + ink + "_" + bg] = c.toDataURL("image/png").split(",")[1];
  }
  const c = document.createElement("canvas");
  c.width = J.SHEET_W * J.SHEETS_PER_ROW; c.height = J.SHEET_H * Math.ceil(J.CORNER_PAIRS.length / J.SHEETS_PER_ROW);
  const x = c.getContext("2d");
  x.fillStyle = "#000"; x.fillRect(0, 0, c.width, c.height);  // no alpha anywhere: the editor drops it
  J.CORNER_PAIRS.forEach(([f, b], n) => {
    const ox0 = (n % J.SHEETS_PER_ROW) * J.SHEET_W; let y0 = Math.floor(n / J.SHEETS_PER_ROW) * J.SHEET_H;
    for (const r of J.RADII) {
      for (let k = 0; k < 4; k++) {  // 0 TL, 1 TR, 2 BL, 3 BR
        const ox = ox0 + k * r, flipX = k & 1, flipY = k >> 1;
        x.save(); x.beginPath(); x.rect(ox, y0, r, r); x.clip();
        x.fillStyle = css(J.THEME[b]); x.fillRect(ox, y0, r, r);
        x.fillStyle = css(J.THEME[f]);
        const cx = ox + (flipX ? 0 : r), cy = y0 + (flipY ? 0 : r);
        x.beginPath(); x.moveTo(cx, cy);
        const a0 = [Math.PI, 1.5 * Math.PI, 0.5 * Math.PI, 0][k], a1 = a0 + Math.PI / 2;
        x.arc(cx, cy, r, a0, a1); x.closePath(); x.fill(); x.restore();
      }
      y0 += r;
    }
  });
  out["corners"] = c.toDataURL("image/png").split(",")[1];
  document.getElementById("out").textContent = JSON.stringify(out);
})().catch(e => { document.getElementById("out").textContent = "ERROR " + e; });
</script>`;

const tmp = path.join(outDir, "_render.html");
fs.mkdirSync(outDir, { recursive: true });
for (const f of fs.readdirSync(outDir)) if (f.endsWith(".png")) fs.unlinkSync(path.join(outDir, f));
fs.writeFileSync(tmp, html);
const r = spawnSync(CHROME, ["--headless=new", "--disable-gpu", "--no-sandbox", "--virtual-time-budget=15000",
  "--dump-dom", "file:///" + tmp.replace(/\\/g, "/")], { maxBuffer: 256 * 1024 * 1024, encoding: "utf8" });
fs.unlinkSync(tmp);
const m = /<pre id="out">([\s\S]*?)<\/pre>/.exec(r.stdout || "");
if (!m || m[1].startsWith("ERROR") || m[1] === "pending") {
  console.error("render failed:", m ? m[1].slice(0, 300) : (r.stderr || "").slice(0, 500));
  process.exit(1);
}
const pics = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, "&"));
const order = [];
for (const s of SIZES) for (const [ink, bg] of INKS) order.push("ic" + s + "_" + ink + "_" + bg);
order.push("corners");
const manifest = { order, icons: names, per_row: PER_ROW, sizes: SIZES, inks: INKS, radii: RADII, corner_pairs: CORNER_PAIRS,
  sheet: [SHEET_W, SHEET_H], sheets_per_row: SHEETS_PER_ROW, files: {} };
for (const name of order) {
  const buf = Buffer.from(pics[name], "base64");
  fs.writeFileSync(path.join(outDir, name + ".png"), buf);
  manifest.files[name] = buf.length;
}
fs.writeFileSync(path.join(outDir, "pics.json"), JSON.stringify(manifest, null, 1));
console.log("wrote", order.length, "PNGs to", outDir);
