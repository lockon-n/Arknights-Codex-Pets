import { ALPHA_MODES, Application, Assets } from "pixi.js";
import { AtlasAttachmentLoader, SkeletonBinary, SkeletonJson, Spine, TextureAtlas } from "@pixi-spine/all-3.8";

let app;
let spine;
let skeletonData;

function loadAtlas(atlasText, baseTexture) {
  return new Promise((resolve, reject) => {
    let atlas;
    try {
      atlas = new TextureAtlas(atlasText, (_page, done) => done(baseTexture), loaded => resolve(loaded || atlas));
    } catch (error) {
      reject(error);
    }
  });
}

function applyPose(animationName, time) {
  spine.state.clearTracks();
  spine.skeleton.setToSetupPose();
  const entry = spine.state.setAnimation(0, animationName, false);
  entry.trackTime = Math.max(0, time);
  spine.state.apply(spine.skeleton);
  spine.skeleton.updateWorldTransform();
  spine.update(0);
}

function renderPose(animationName, time, framing) {
  applyPose(animationName, time);
  const canvas = app.view;
  spine.scale.set(framing.scale);
  spine.position.set(canvas.width / 2 - framing.centerX * framing.scale, canvas.height / 2 - framing.centerY * framing.scale);
  app.renderer.render(app.stage);
  return canvas;
}

function renderAdjustedPose(animationName, time, framing, adjustments = []) {
  applyPose(animationName, time);
  for (const adjustment of adjustments) {
    const bone = spine.skeleton.findBone(adjustment.bone);
    if (!bone) continue;
    bone.x += adjustment.x || 0;
    bone.y += adjustment.y || 0;
    bone.rotation += adjustment.rotation || 0;
  }
  spine.state.clearTracks();
  spine.skeleton.updateWorldTransform();
  spine.update(0);
  const canvas = app.view;
  spine.scale.set(framing.scale);
  spine.position.set(canvas.width / 2 - framing.centerX * framing.scale, canvas.height / 2 - framing.centerY * framing.scale);
  app.renderer.render(app.stage);
  const controls = adjustments.map(adjustment => {
    const bone = spine.skeleton.findBone(adjustment.bone);
    if (!bone) return { bone: adjustment.bone, missing: true };
    const worldX = bone.matrix?.tx ?? null;
    const worldY = bone.matrix?.ty ?? null;
    return {
      bone: adjustment.bone,
      worldX,
      worldY,
      screenX: worldX == null ? null : spine.position.x + worldX * spine.scale.x,
      screenY: worldY == null ? null : spine.position.y + worldY * spine.scale.y,
      applied: {
        x: adjustment.x || 0,
        y: adjustment.y || 0,
        rotation: adjustment.rotation || 0,
      },
    };
  });
  return { canvas, controls };
}

window.spineRenderer = {
  async init({ atlasUrl, imageUrl, skeletonUrl, skeletonFormat, width = 384, height = 416 }) {
    const canvas = document.getElementById("stage");
    canvas.width = width;
    canvas.height = height;
    app = new Application({ view: canvas, width, height, backgroundAlpha: 0, antialias: false, resolution: 1, preserveDrawingBuffer: true });
    const [atlasText, skeletonResponse, texture] = await Promise.all([
      fetch(atlasUrl).then(response => response.text()),
      fetch(skeletonUrl),
      Assets.load(imageUrl),
    ]);
    texture.baseTexture.alphaMode = ALPHA_MODES.PMA;
    const atlas = await loadAtlas(atlasText, texture.baseTexture);
    const attachmentLoader = new AtlasAttachmentLoader(atlas);
    let parser;
    let skeletonInput;
    if (skeletonFormat === "json") {
      parser = new SkeletonJson(attachmentLoader);
      skeletonInput = await skeletonResponse.json();
    } else {
      parser = new SkeletonBinary(attachmentLoader);
      skeletonInput = new Uint8Array(await skeletonResponse.arrayBuffer());
    }
    parser.scale = 1;
    skeletonData = parser.readSkeletonData(skeletonInput);
    spine = new Spine(skeletonData);
    spine.autoUpdate = false;
    app.stage.addChild(spine);
    spine.skeleton.setToSetupPose();
    spine.skeleton.updateWorldTransform();
    return {
      animations: skeletonData.animations.map(animation => ({ name: animation.name, duration: animation.duration })),
      skeleton: { x: skeletonData.x, y: skeletonData.y, width: skeletonData.width, height: skeletonData.height, version: skeletonData.version },
      bones: spine.skeleton.bones.map(bone => ({
        name: bone.data.name,
        parent: bone.parent ? bone.parent.data.name : null,
        x: bone.data.x,
        y: bone.data.y,
        rotation: bone.data.rotation,
        worldX: bone.matrix?.tx ?? null,
        worldY: bone.matrix?.ty ?? null,
        childCount: spine.skeleton.bones.filter(candidate => candidate.parent === bone).length,
      })),
      slots: spine.skeleton.slots.map(slot => ({
        name: slot.data.name,
        bone: slot.bone.data.name,
        setupAttachment: slot.data.attachmentName || null,
        currentAttachment: slot.attachment?.name || null,
        blendMode: slot.data.blendMode ?? null,
      })),
    };
  },
  measure(animationName, times) {
    return times.map(time => {
      applyPose(animationName, time);
      const bounds = spine.getLocalBounds();
      return { time, x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height };
    });
  },
  render(animationName, time, framing) {
    return renderPose(animationName, time, framing).toDataURL("image/png");
  },
  visibleBounds(animationName, time, framing) {
    const canvas = renderPose(animationName, time, framing);
    const probe = document.createElement("canvas");
    probe.width = canvas.width;
    probe.height = canvas.height;
    const context = probe.getContext("2d", { willReadFrequently: true });
    context.drawImage(canvas, 0, 0);
    const pixels = context.getImageData(0, 0, probe.width, probe.height).data;
    let minX = probe.width;
    let minY = probe.height;
    let maxX = -1;
    let maxY = -1;
    for (let y = 0; y < probe.height; y += 1) {
      for (let x = 0; x < probe.width; x += 1) {
        if (pixels[(y * probe.width + x) * 4 + 3] === 0) continue;
        minX = Math.min(minX, x);
        minY = Math.min(minY, y);
        maxX = Math.max(maxX, x);
        maxY = Math.max(maxY, y);
      }
    }
    if (maxX < minX || maxY < minY) return null;
    return { x: minX, y: minY, width: maxX - minX + 1, height: maxY - minY + 1 };
  },
  renderAdjusted(animationName, time, framing, adjustments = []) {
    return renderAdjustedPose(animationName, time, framing, adjustments).canvas.toDataURL("image/png");
  },
  renderAdjustedWithMetadata(animationName, time, framing, adjustments = []) {
    const result = renderAdjustedPose(animationName, time, framing, adjustments);
    return { dataUrl: result.canvas.toDataURL("image/png"), controls: result.controls };
  },
};
