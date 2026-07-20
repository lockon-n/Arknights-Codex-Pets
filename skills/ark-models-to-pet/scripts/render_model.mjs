#!/usr/bin/env node
import http from "node:http";
import { createRequire } from "node:module";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";


function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    if (!key?.startsWith("--") || argv[index + 1] == null) throw new Error(`invalid argument near ${key}`);
    result[key.slice(2)] = argv[index + 1];
  }
  return result;
}

function findPlaywright() {
  const candidates = [
    process.env.CODEX_NODE_MODULES,
    path.join(process.env.HOME || "", ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules"),
  ].filter(Boolean);
  for (const base of candidates) {
    try {
      const localRequire = createRequire(path.join(base, "package.json"));
      return localRequire("playwright");
    } catch {}
  }
  throw new Error("Playwright not found. Set CODEX_NODE_MODULES to the bundled workspace node_modules path.");
}

function safeFolder(name) {
  return name.replace(/[^a-zA-Z0-9._-]+/g, "_");
}

const args = parseArgs(process.argv.slice(2));
for (const required of ["model-dir", "runtime-dir", "output-dir"]) {
  if (!args[required]) throw new Error(`missing --${required}`);
}
const modelDir = path.resolve(args["model-dir"]);
const runtimeDir = path.resolve(args["runtime-dir"]);
const outputDir = path.resolve(args["output-dir"]);
const width = Number(args.width || 768);
const height = Number(args.height || 832);
const frameCount = Number(args.frames || 8);
const framingMode = args.framing || "visible";
if (!new Set(["skeleton", "visible"]).has(framingMode)) throw new Error("--framing must be skeleton or visible");

const manifestPath = path.join(modelDir, "model-manifest.json");
let manifest = null;
try { manifest = JSON.parse(await readFile(manifestPath, "utf8")); } catch {}
const assetList = manifest?.metadata?.assetList || {};
const directoryFiles = (await import("node:fs/promises")).readdir(modelDir);
const files = await directoryFiles;
const atlasName = assetList[".atlas"] || files.find(file => file.endsWith(".atlas"));
const imageName = assetList[".png"] || files.find(file => file.endsWith(".png"));
const skeletonName = assetList[".skel"] || assetList[".json"] || files.find(file => file.endsWith(".skel")) || files.find(file => file.endsWith(".json") && !file.includes("manifest"));
if (!atlasName || !imageName || !skeletonName) throw new Error("model directory must contain atlas, png, and skel/json skeleton files");

const bundlePath = path.join(runtimeDir, "bundle.js");
await mkdir(outputDir, { recursive: true });
const mime = { ".html": "text/html", ".js": "text/javascript", ".atlas": "text/plain", ".png": "image/png", ".skel": "application/octet-stream", ".json": "application/json" };
const server = http.createServer(async (request, response) => {
  try {
    const url = new URL(request.url, "http://127.0.0.1");
    let file;
    if (url.pathname === "/") {
      response.writeHead(200, { "Content-Type": "text/html" });
      return response.end('<!doctype html><canvas id="stage"></canvas><script src="/bundle.js"></script>');
    }
    if (url.pathname === "/bundle.js") file = bundlePath;
    else if (url.pathname.startsWith("/assets/")) file = path.join(modelDir, path.basename(decodeURIComponent(url.pathname)));
    else return response.writeHead(404).end();
    response.writeHead(200, { "Content-Type": mime[path.extname(file)] || "application/octet-stream" });
    response.end(await readFile(file));
  } catch (error) {
    response.writeHead(500).end(String(error));
  }
});

await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const address = server.address();
const { chromium } = findPlaywright();
const launchOptions = { headless: true };
const chromeCandidates = [
  process.env.CHROME_EXECUTABLE,
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
].filter(Boolean);
for (const candidate of chromeCandidates) {
  try {
    const stat = await (await import("node:fs/promises")).stat(candidate);
    if (stat.isFile()) { launchOptions.executablePath = candidate; break; }
  } catch {}
}
const browser = await chromium.launch(launchOptions);
try {
  const page = await browser.newPage();
  await page.goto(`http://127.0.0.1:${address.port}/`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => Boolean(window.spineRenderer));
  const metadata = await page.evaluate(config => window.spineRenderer.init(config), {
    atlasUrl: `/assets/${encodeURIComponent(atlasName)}`,
    imageUrl: `/assets/${encodeURIComponent(imageName)}`,
    skeletonUrl: `/assets/${encodeURIComponent(skeletonName)}`,
    skeletonFormat: skeletonName.endsWith(".json") ? "json" : "binary",
    width,
    height,
  });
  const requested = args.animations ? new Set(args.animations.split(",")) : null;
  const animations = metadata.animations.filter(animation => !requested || requested.has(animation.name));
  if (!animations.length) throw new Error("no matching animations to render");

  const measurements = [];
  for (const animation of animations) {
    const times = Array.from({ length: frameCount }, (_, index) => animation.duration ? animation.duration * index / frameCount : 0);
    const bounds = await page.evaluate(({ name, times }) => window.spineRenderer.measure(name, times), { name: animation.name, times });
    measurements.push({ animation: animation.name, duration: animation.duration, times, bounds });
  }
  const allBounds = measurements.flatMap(item => item.bounds);
  const minX = Math.min(...allBounds.map(bound => bound.x));
  const minY = Math.min(...allBounds.map(bound => bound.y));
  const maxX = Math.max(...allBounds.map(bound => bound.x + bound.width));
  const maxY = Math.max(...allBounds.map(bound => bound.y + bound.height));
  const unionWidth = Math.max(1, maxX - minX);
  const unionHeight = Math.max(1, maxY - minY);
  const skeletonFraming = {
    centerX: (minX + maxX) / 2,
    centerY: (minY + maxY) / 2,
    scale: Math.min(width * 0.88 / unionWidth, height * 0.88 / unionHeight),
  };
  let framing = skeletonFraming;
  let visibleProbe = null;
  if (framingMode === "visible") {
    const visibleBounds = [];
    for (const item of measurements) {
      for (const time of item.times) {
        const bound = await page.evaluate(
          ({ name, time, framing }) => window.spineRenderer.visibleBounds(name, time, framing),
          { name: item.animation, time, framing: skeletonFraming },
        );
        if (bound) visibleBounds.push(bound);
      }
    }
    if (!visibleBounds.length) throw new Error("visible framing found no rendered pixels");
    const pixelMinX = Math.min(...visibleBounds.map(bound => bound.x));
    const pixelMinY = Math.min(...visibleBounds.map(bound => bound.y));
    const pixelMaxX = Math.max(...visibleBounds.map(bound => bound.x + bound.width));
    const pixelMaxY = Math.max(...visibleBounds.map(bound => bound.y + bound.height));
    const pixelWidth = Math.max(1, pixelMaxX - pixelMinX);
    const pixelHeight = Math.max(1, pixelMaxY - pixelMinY);
    const pixelCenterX = (pixelMinX + pixelMaxX) / 2;
    const pixelCenterY = (pixelMinY + pixelMaxY) / 2;
    const correction = Math.min(width * 0.88 / pixelWidth, height * 0.88 / pixelHeight);
    framing = {
      centerX: skeletonFraming.centerX + (pixelCenterX - width / 2) / skeletonFraming.scale,
      centerY: skeletonFraming.centerY + (pixelCenterY - height / 2) / skeletonFraming.scale,
      scale: skeletonFraming.scale * correction,
    };
    visibleProbe = { x: pixelMinX, y: pixelMinY, width: pixelWidth, height: pixelHeight, correction };
  }

  const rendered = [];
  for (const item of measurements) {
    const folder = safeFolder(item.animation);
    const animationDir = path.join(outputDir, "animations", folder);
    await mkdir(animationDir, { recursive: true });
    for (let index = 0; index < item.times.length; index++) {
      const dataUrl = await page.evaluate(({ name, time, framing }) => window.spineRenderer.render(name, time, framing), { name: item.animation, time: item.times[index], framing });
      await writeFile(path.join(animationDir, `${String(index).padStart(2, "0")}.png`), Buffer.from(dataUrl.split(",", 2)[1], "base64"));
    }
    rendered.push({ name: item.animation, folder, duration: item.duration, times: item.times });
  }

  let lookControls = null;
  if (args["look-config"]) {
    const config = JSON.parse(await readFile(path.resolve(args["look-config"]), "utf8"));
    if (config.mode === "directions" && config.review_required !== false) {
      throw new Error("look config must have review_required=false before rendering production directions");
    }
    const lookDir = path.join(outputDir, config.mode === "candidates" ? "look-candidates" : "look-source");
    await mkdir(lookDir, { recursive: true });
    let poses;
    if (config.mode === "candidates") {
      const eye = (x, y) => (config.eye_bones || []).map(bone => ({ bone, x, y }));
      poses = [
        ["neutral", []], ["eye-x-plus", eye(config.eye_step || 8, 0)], ["eye-x-minus", eye(-(config.eye_step || 8), 0)],
        ["eye-y-plus", eye(0, config.eye_step || 8)], ["eye-y-minus", eye(0, -(config.eye_step || 8))],
        ["head-x-plus", config.head_bone ? [{ bone: config.head_bone, x: config.head_step || 3 }] : []],
        ["head-x-minus", config.head_bone ? [{ bone: config.head_bone, x: -(config.head_step || 3) }] : []],
        ["head-y-plus", config.head_bone ? [{ bone: config.head_bone, y: config.head_y_step || config.head_step || 3 }] : []],
        ["head-y-minus", config.head_bone ? [{ bone: config.head_bone, y: -(config.head_y_step || config.head_step || 3) }] : []],
        ["head-rot-plus", config.head_bone ? [{ bone: config.head_bone, rotation: config.head_rotation_step || 6 }] : []],
        ["head-rot-minus", config.head_bone ? [{ bone: config.head_bone, rotation: -(config.head_rotation_step || 6) }] : []],
      ];
    } else {
      const labels = ["000", "022.5", "045", "067.5", "090", "112.5", "135", "157.5", "180", "202.5", "225", "247.5", "270", "292.5", "315", "337.5"];
      poses = labels.map(label => {
        const radians = Number(label) * Math.PI / 180;
        const horizontal = Math.sin(radians);
        const verticalUp = Math.cos(radians);
        const adjustments = (config.eye_bones || []).map(bone => ({
          bone,
          x: (config.eye_x_up || 0) * verticalUp + (config.eye_x_right || 0) * horizontal,
          y: (config.eye_y_up || 0) * verticalUp + (config.eye_y_right || 0) * horizontal,
        }));
        if (config.head_bone) adjustments.push({
          bone: config.head_bone,
          x: (config.head_x_up || 0) * verticalUp + (config.head_x_right || 0) * horizontal,
          y: (config.head_y_up || 0) * verticalUp + (config.head_y_right || 0) * horizontal,
          rotation: (config.head_rotation_up || 0) * verticalUp + (config.head_rotation_right || 0) * horizontal,
        });
        return [label, adjustments];
      });
    }
    const lookPoses = [];
    for (const [label, adjustments] of poses) {
      const result = await page.evaluate(({ name, time, framing, adjustments }) => window.spineRenderer.renderAdjustedWithMetadata(name, time, framing, adjustments), {
        name: config.animation, time: config.time || 0, framing, adjustments,
      });
      await writeFile(path.join(lookDir, `${label}.png`), Buffer.from(result.dataUrl.split(",", 2)[1], "base64"));
      lookPoses.push({ label, controls: result.controls });
    }
    lookControls = { mode: config.mode, poses: lookPoses };
  }

  await writeFile(path.join(outputDir, "render-metadata.json"), JSON.stringify({ model: { atlasName, imageName, skeletonName }, ...metadata, framingMode, skeletonFraming, visibleProbe, framing, rendered, lookControls }, null, 2));
  process.stdout.write(`${outputDir}\n`);
} finally {
  await browser.close();
  server.close();
}
