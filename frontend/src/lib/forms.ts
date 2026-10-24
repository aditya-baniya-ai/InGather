import type { PlanDraft } from "./api";
import { utcToLocal, type LocalWindow } from "./time";
import { ACTIVITIES, INTENTS } from "./vocab";

export const MIN_PASSWORD = 8;

/** Join form: `mismatch` only once the user has typed a confirmation; `ok` gates submit. */
export function passwordCheck(password: string, confirm: string) {
  const tooShort = password.length < MIN_PASSWORD;
  const mismatch = confirm.length > 0 && confirm !== password;
  return { tooShort, mismatch, ok: !tooShort && confirm === password };
}

export interface PlanForm {
  activity: string;
  title: string;
  goal: string;
  city: string;
  timezone: string;
  startDate: string;
  endDate: string;
  windows: LocalWindow[];
  interests: string[];
  intent: string;
  size: [number, number];
  groupOnly: boolean;
}
export type FormKey = keyof PlanForm;

/** PlanDraftOut field names (as listed in `missing`) -> what the user should add. */
export const MISSING_COPY: Record<string, string> = {
  activity_type: "What kind of plan it is",
  title: "A title",
  goal_text: "Your goal",
  city: "The city or region",
  timezone: "The time zone",
  start_date: "Your start date",
  end_date: "Your end date",
  intent: "What you're looking for",
  interests: "A few interests",
  group_min: "Group size",
  group_max: "Group size",
  group_only: "Whether it's group-only",
  windows: "When you're free",
};

/**
 * Intake draft -> a patch for the plan form, plus which fields the agent filled. UTC windows become
 * wall-clock times in the draft's timezone (or the form's). Unknown values are left for the user.
 */
export function draftToForm(d: PlanDraft, current: Pick<PlanForm, "timezone" | "goal">): { patch: Partial<PlanForm>; filled: FormKey[] } {
  const tz = d.timezone || current.timezone;
  const windows = d.windows.map((w) => {
    const s = utcToLocal(w.starts_at, tz);
    return { date: s.date, from: s.time, to: utcToLocal(w.ends_at, tz).time };
  });
  const days = windows.map((w) => w.date).sort();
  const start = d.start_date ?? days[0] ?? null;
  const end = d.end_date ?? days.at(-1) ?? start;
  const patch: Partial<PlanForm> = {
    activity: ACTIVITIES.some((a) => a.value === d.activity_type) ? d.activity_type! : undefined,
    title: d.title ?? undefined,
    goal: d.goal_text || current.goal,
    city: d.city ?? undefined,
    timezone: d.timezone ?? undefined,
    startDate: start ?? undefined,
    endDate: end ?? undefined,
    windows: windows.length ? windows : undefined,
    interests: d.interests.length ? d.interests.map((t) => t.toLowerCase()).slice(0, 10) : undefined,
    intent: INTENTS.some((i) => i.value === d.intent) ? d.intent! : undefined,
    size: d.group_min && d.group_max ? [d.group_min, d.group_max] : undefined,
    groupOnly: d.group_only ?? undefined,
  };
  for (const k of Object.keys(patch) as FormKey[]) if (patch[k] === undefined) delete patch[k];
  const filled = (Object.keys(patch) as FormKey[]).filter((k) => k !== "goal" || !!d.goal_text);
  return { patch, filled };
}
