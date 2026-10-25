import type { AgeRange, Gender, Me, MePatch } from "./api";

export const GENDERS: { value: Gender | ""; label: string }[] = [
  { value: "", label: "Not set" }, { value: "woman", label: "Woman" }, { value: "man", label: "Man" },
  { value: "non_binary", label: "Non-binary" }, { value: "self_describe", label: "Self-describe" }, { value: "prefer_not_to_say", label: "Prefer not to say" },
];
export const AGE_RANGES: { value: AgeRange | ""; label: string }[] = [
  { value: "", label: "Not set" }, ...(["18-24", "25-34", "35-44", "45-54", "55+"] as AgeRange[]).map((v) => ({ value: v, label: v.replace("-", "–") })),
];

export interface AboutForm {
  gender: Gender | ""; genderSelf: string; ageRange: AgeRange | ""; education: string; work: string;
  showGender: boolean; showAge: boolean; showBackground: boolean;
}

export const aboutFromMe = (me: Me): AboutForm => ({
  gender: me.gender ?? "", genderSelf: me.gender_self ?? "", ageRange: me.age_range ?? "", education: me.education ?? "", work: me.work ?? "",
  showGender: !!me.show_gender, showAge: !!me.show_age, showBackground: !!me.show_background,
});

/** "" clears a field server-side; the self-description is only sent with "Self-describe". */
export const aboutPatch = (f: AboutForm): MePatch => ({
  gender: f.gender, gender_self: f.gender === "self_describe" ? f.genderSelf.trim() : "", age_range: f.ageRange,
  education: f.education.trim(), work: f.work.trim(), show_gender: f.showGender, show_age: f.showAge, show_background: f.showBackground,
});

export const MAX_PHOTO = 3 * 1024 * 1024;
const PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp"];

/** Client-side pre-check (the server re-checks the actual bytes). */
export function photoError(file: File): string | null {
  if (!PHOTO_TYPES.includes(file.type)) return "Use a JPEG, PNG or WebP image.";
  if (file.size > MAX_PHOTO) return "That photo is over 3 MB. Try a smaller one.";
  return null;
}
