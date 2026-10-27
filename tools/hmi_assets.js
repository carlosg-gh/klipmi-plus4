// SPDX-License-Identifier: GPL-3.0-or-later
// Render the HMI picture assets (icon strips, anti-aliased corner sheets) to PNG.
// No dependencies: headless Chrome draws on a canvas, we pull the PNGs out of --dump-dom.
//
//   node tools/hmi_assets.js [outdir]      (default hmi/plus4-canvas/assets/pics)
//
// Input: hmi/plus4-canvas/assets/svg/<name>.svg (Material Symbols, Apache-2.0).
// Output: PNGs plus pics.json (layout manifest read by the canvas code and the editor guide).
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const root = path.join(__dirname, "..", "hmi", "plus4-canvas", "assets");
const outDir = process.argv[2] || path.join(root, "pics");
const CHROME = process.env.CHROME || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";

// Mirrors Theme in src/klipmi/canvas/gfx.py.
const THEME = {
  bg: [14, 16, 20], surface: [30, 34, 41], surface2: [44, 49, 58], raised: [58, 64, 75],
  accent: [0, 180, 235], accent_dim: [0, 92, 124], err_dim: [110, 32, 36],
};
// icon name -> Material Symbols svg file
const ICONS = {
  nozzle: "mode_heat", bed: "grid_on", chamber: "deployed_code", fan: "mode_fan", light: "lightbulb",
  spool: "donut_large", home: "home", control: "tune", files: "folder", box: "inventory_2",
  gear: "settings", play: "play_arrow", pause: "pause", stop: "stop", up: "arrow_upward",
  down: "arrow_downward", left: "arrow_back", right: "arrow_forward", check: "check", warning: "warning",
};
const ICON_SIZES = [24, 32];
const ICON_BGS = ["bg", "surface", "surface2", "raised", "accent", "accent_dim"];
const RADII = [4, 6, 8, 10, 12, 16, 20, 24];
const CORNER_PAIRS = [
  ["surface", "bg"], ["surface2", "surface"], ["raised", "surface"], ["surface2", "bg"], ["raised", "bg"],
  ["accent", "bg"], ["accent", "surface"], ["accent_dim", "surface"], ["err_dim", "surface"], ["bg", "surface"],
];

const icons = Object.entries(ICONS).map(([name, file]) => {
  let svg = fs.readFileSync(path.join(root, "svg", file + ".svg"), "utf8");
  svg = svg.replace("<svg ", '<svg fill="#ffffff" ');
  return { name, data: "data:image/svg+xml;base64," + Buffer.from(svg).toString("base64") };
});

const job = { THEME, icons, ICON_SIZES, ICON_BGS, RADII, CORNER_PAIRS };
const html = `<!doctype html><meta charset=utf-8><pre id=out>pending</pre><script>
const J = ${JSON.stringify(job)};
const css = c => "rgb(" + c.join(",") + ")";
const load = src => new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = src; });
(async () => {
  const out = {};
  const imgs = await Promise.all(J.icons.map(i => load(i.data)));
  for (const s of J.ICON_SIZES) for (const bg of J.ICON_BGS) {
    const c = document.createElement("canvas"); c.width = s * imgs.length; c.height = s;
    const x = c.getContext("2d"); x.fillStyle = css(J.THEME[bg]); x.fillRect(0, 0, c.width, c.height);
    x.imageSmoothingQuality = "high";
    imgs.forEach((im, k) => x.drawImage(im, k * s, 0, s, s));
    out["ic" + s + "_" + bg] = c.toDataURL("image/png").split(",")[1];
  }
  const H = J.RADII.reduce((a, b) => a + b, 0), W = 4 * Math.max(...J.RADII);
  for (const [f, b] of J.CORNER_PAIRS) {
    const c = document.createElement("canvas"); c.width = W; c.height = H;
    const x = c.getContext("2d"); let y0 = 0;
    for (const r of J.RADII) {
      for (let k = 0; k < 4; k++) {  // 0 TL, 1 TR, 2 BL, 3 BR
        const ox = k * r, flipX = k & 1, flipY = k >> 1;
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
    out["cr_" + f + "_" + b] = c.toDataURL("image/png").split(",")[1];
  }
  document.getElementById("out").textContent = JSON.stringify(out);
})().catch(e => { document.getElementById("out").textContent = "ERROR " + e; });
</script>`;

const tmp = path.join(outDir, "_render.html");
fs.mkdirSync(outDir, { recursive: true });
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
const manifest = { icons: Object.keys(ICONS), icon_sizes: ICON_SIZES, icon_bgs: ICON_BGS, radii: RADII, corner_pairs: CORNER_PAIRS, files: {} };
for (const [name, b64] of Object.entries(pics)) {
  const buf = Buffer.from(b64, "base64");
  fs.writeFileSync(path.join(outDir, name + ".png"), buf);
  manifest.files[name] = buf.length;
}
fs.writeFileSync(path.join(outDir, "pics.json"), JSON.stringify(manifest, null, 1));
console.log("wrote", Object.keys(pics).length, "PNGs to", outDir);
