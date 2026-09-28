import { describe, expect, it } from "vitest";
import { fitWithin, imageFromClipboard, isUsableRect, MAX_PIXELS, MAX_SIDE, rectFromPoints } from "./image";

describe("fitWithin (downscale before the vision call)", () => {
  it("never scales small images up", () => {
    expect(fitWithin(400, 300)).toEqual({ w: 400, h: 300 });
  });
  it("caps the long side", () => {
    const r = fitWithin(4000, 1000);
    expect(r.w).toBeLessThanOrEqual(MAX_SIDE);
    expect(r.w / r.h).toBeCloseTo(4, 1);
  });
  it("caps total pixels (phone photos)", () => {
    const r = fitWithin(4032, 3024);
    expect(r.w * r.h).toBeLessThanOrEqual(MAX_PIXELS * 1.01);
    expect(Math.max(r.w, r.h)).toBeLessThanOrEqual(MAX_SIDE);
    expect(r.w / r.h).toBeCloseTo(4032 / 3024, 1);
  });
});

describe("crop rectangle", () => {
  it("works in any drag direction and clamps to the image", () => {
    expect(rectFromPoints(300, 200, 100, 50, 1000, 800)).toEqual({ x: 100, y: 50, w: 200, h: 150 });
    expect(rectFromPoints(-20, -20, 2000, 2000, 1000, 800)).toEqual({ x: 0, y: 0, w: 1000, h: 800 });
  });
  it("treats a click (tiny drag) as no selection", () => {
    expect(isUsableRect({ x: 10, y: 10, w: 3, h: 3 })).toBe(false);
    expect(isUsableRect(null)).toBe(false);
    expect(isUsableRect({ x: 0, y: 0, w: 50, h: 40 })).toBe(true);
  });
});

describe("clipboard screenshots", () => {
  const dt = (items: { kind: string; type: string }[]) =>
    ({ items: items.map((i) => ({ ...i, getAsFile: () => new File(["x"], "s.png", { type: i.type }) })) }) as unknown as DataTransfer;
  it("finds a pasted image", () => {
    expect(imageFromClipboard(dt([{ kind: "string", type: "text/plain" }, { kind: "file", type: "image/png" }]))?.type).toBe("image/png");
  });
  it("ignores text-only pastes", () => {
    expect(imageFromClipboard(dt([{ kind: "string", type: "text/plain" }]))).toBeNull();
    expect(imageFromClipboard(null)).toBeNull();
  });
});
