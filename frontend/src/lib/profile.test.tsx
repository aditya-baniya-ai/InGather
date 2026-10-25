import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { DetailChips } from "../components/ui";
import type { Me } from "./api";
import { aboutFromMe, aboutPatch, photoError } from "./profile";

const me = { gender: "self_describe", gender_self: "Agender", age_range: "25-34", education: null, work: "Dell", show_gender: true } as unknown as Me;

describe("about-you form mapping", () => {
  it("fills blanks and defaults every switch to off", () => {
    expect(aboutFromMe({} as Me)).toEqual({ gender: "", genderSelf: "", ageRange: "", education: "", work: "", showGender: false, showAge: false, showBackground: false });
  });
  it("round-trips and only sends a self-description with self_describe", () => {
    const f = aboutFromMe(me);
    expect(aboutPatch({ ...f, work: "  Dell " })).toMatchObject({ gender: "self_describe", gender_self: "Agender", age_range: "25-34", work: "Dell", education: "", show_gender: true, show_age: false });
    expect(aboutPatch({ ...f, gender: "woman" }).gender_self).toBe("");
  });
  it("pre-checks photo type and size", () => {
    expect(photoError(new File(["x"], "a.gif", { type: "image/gif" }))).toMatch(/JPEG/);
    expect(photoError(new File([new Uint8Array(3 * 1024 * 1024 + 1)], "a.png", { type: "image/png" }))).toMatch(/3 MB/);
    expect(photoError(new File(["x"], "a.webp", { type: "image/webp" }))).toBeNull();
  });
});

describe("DetailChips", () => {
  it("renders one chip per shown detail and nothing when empty", () => {
    const { container, rerender } = render(<DetailChips details={["Woman", "25–34"]} />);
    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Woman", "25–34"]);
    rerender(<DetailChips details={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
