// @vitest-environment node
import { describe, expect, it } from "vitest";
import { encodeWav } from "./wav";

const ascii = (v: DataView, at: number, n: number) => String.fromCharCode(...Array.from({ length: n }, (_, i) => v.getUint8(at + i)));

describe("encodeWav", () => {
  it("writes a valid 16-bit PCM mono RIFF header and clamped samples", async () => {
    const samples = new Float32Array([0, 1, -1, 0.5, 2, -2]);
    const blob = encodeWav(samples, 16000);
    expect(blob.type).toBe("audio/wav");
    const v = new DataView(await blob.arrayBuffer());
    expect(v.byteLength).toBe(44 + samples.length * 2);
    expect(ascii(v, 0, 4)).toBe("RIFF");
    expect(v.getUint32(4, true)).toBe(36 + samples.length * 2);
    expect(ascii(v, 8, 4)).toBe("WAVE");
    expect(ascii(v, 12, 4)).toBe("fmt ");
    expect(v.getUint16(20, true)).toBe(1); // PCM
    expect(v.getUint16(22, true)).toBe(1); // mono
    expect(v.getUint32(24, true)).toBe(16000);
    expect(v.getUint32(28, true)).toBe(32000);
    expect(v.getUint16(32, true)).toBe(2);
    expect(v.getUint16(34, true)).toBe(16);
    expect(ascii(v, 36, 4)).toBe("data");
    expect(v.getUint32(40, true)).toBe(samples.length * 2);
    const pcm = Array.from({ length: samples.length }, (_, i) => v.getInt16(44 + i * 2, true));
    expect(pcm).toEqual([0, 32767, -32768, 16383, 32767, -32768]);
  });
});
