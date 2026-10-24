import { useState, type FormEvent, type ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Lock, Plus, ShieldCheck, Trash2 } from "lucide-react";
import { AppShell } from "../components/AppShell";
import { VoiceButton } from "../components/VoiceButton";
import { Button, Chip, cx, InlineError, Panel, SelectField, Switch, TextArea, TextField } from "../components/ui";
import { api, type DiscoveryMode } from "../lib/api";
import { keys } from "../lib/hooks";
import { browserTimeZone, TIMEZONES, windowsToUtc, type LocalWindow } from "../lib/time";
import { ACTIVITIES, DISCOVERY, INTENTS, INTEREST_SUGGESTIONS } from "../lib/vocab";

function Fieldset({ legend, children, hint }: { legend: string; children: ReactNode; hint?: string }) {
  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="mb-2 text-[14px] font-medium">{legend}</legend>
      {hint && <p className="-mt-2 text-[13px] text-muted">{hint}</p>}
      {children}
    </fieldset>
  );
}

const nextWeek = () => { const d = new Date(Date.now() + 7 * 864e5); return d.toISOString().slice(0, 10); };

export function CreatePlan() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const tz0 = browserTimeZone();
  const [activity, setActivity] = useState(params.get("activity") ?? "conference");
  const [title, setTitle] = useState("");
  const [goal, setGoal] = useState(params.get("goal") ?? "");
  const [city, setCity] = useState("");
  const [timezone, setTimezone] = useState(TIMEZONES.includes(tz0) ? tz0 : "America/Chicago");
  const [startDate, setStartDate] = useState(nextWeek());
  const [endDate, setEndDate] = useState(nextWeek());
  const [windows, setWindows] = useState<LocalWindow[]>([{ date: nextWeek(), from: "17:00", to: "21:00" }]);
  const [interests, setInterests] = useState<string[]>([]);
  const [custom, setCustom] = useState("");
  const [intent, setIntent] = useState("friends");
  const [size, setSize] = useState<[number, number]>([3, 4]);
  const [groupOnly, setGroupOnly] = useState(true);
  const [preview, setPreview] = useState("");
  const [mode, setMode] = useState<DiscoveryMode>("private_browse");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const toggleInterest = (t: string) => setInterests((xs) => (xs.includes(t) ? xs.filter((x) => x !== t) : [...xs, t].slice(0, 10)));
  const setWindow = (i: number, patch: Partial<LocalWindow>) => setWindows((ws) => ws.map((w, j) => (j === i ? { ...w, ...patch } : w)));

  const changeStart = (d: string) => {
    setStartDate(d);
    if (endDate < d) setEndDate(d);
    setWindows((ws) => ws.map((w) => (w.date < d ? { ...w, date: d } : w)));
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setProblem(null); setError(null);
    if (endDate < startDate) return setProblem("The end date must be on or after the start date.");
    if (windows.some((w) => w.date < startDate || w.date > endDate)) return setProblem("Each free time must fall within your dates.");
    if (windows.length === 0) return setProblem("Add at least one time you're free.");
    setBusy(true);
    try {
      const plan = await api.createPlan({
        activity_type: activity, title: title.trim(), goal_text: goal.trim(), city: city.trim(), timezone,
        start_date: startDate, end_date: endDate, intent, interests, group_min: size[0], group_max: size[1],
        group_only: groupOnly, preview_text: preview.trim() || null, windows: windowsToUtc(windows, timezone),
      });
      const saved = mode !== plan.discovery_mode || consent ? await api.setDiscovery(plan.id, mode, consent) : plan;
      qc.setQueryData(keys.plan(saved.id), saved);
      qc.invalidateQueries({ queryKey: keys.plans });
      navigate(`/plans/${saved.id}`, { state: { created: true } });
    } catch (err) { setError(err); } finally { setBusy(false); }
  };

  return (
    <AppShell>
      <header className="mb-6">
        <h1 className="font-display text-[36px] leading-[1.05] sm:text-[44px]">New private plan</h1>
        <p className="mt-1 flex items-center gap-1.5 text-[15px] text-muted"><Lock className="size-4" aria-hidden /> Your private itinerary is not public.</p>
      </header>

      <form onSubmit={submit} className="flex flex-col gap-5">
        <Panel className="flex flex-col gap-5 p-5 sm:p-6">
          <Fieldset legend="What kind of plan?">
            <div className="flex flex-wrap gap-2">
              {ACTIVITIES.map((a) => <Chip key={a.value} selected={activity === a.value} onClick={() => setActivity(a.value)}>{a.label}</Chip>)}
            </div>
          </Fieldset>
          <TextField label="Title" value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={120} placeholder="Philly tech conference, evenings free" />
          <div className="flex flex-col gap-2">
            <TextArea label="Your goal, in your words" rows={4} value={goal} onChange={(e) => setGoal(e.target.value)} required maxLength={2000}
              placeholder="I'm in Philadelphia for a tech conference Jan 17–19 and would love to explore after 5 PM."
              hint="Private. Only you and, with your consent, your Gather Agent read this." />
            <VoiceButton onText={(t) => setGoal((g) => (g ? `${g} ${t}` : t))} />
          </div>
        </Panel>

        <Panel className="flex flex-col gap-5 p-5 sm:p-6">
          <div className="grid gap-4 sm:grid-cols-2">
            <TextField label="City or region" value={city} onChange={(e) => setCity(e.target.value)} required maxLength={80} placeholder="Philadelphia" />
            <SelectField label="Time zone" value={timezone} onChange={(e) => setTimezone(e.target.value)}
              options={TIMEZONES.map((z) => ({ value: z, label: z.replace(/_/g, " ") }))} />
            <TextField label="From" type="date" value={startDate} onChange={(e) => changeStart(e.target.value)} required />
            <TextField label="To" type="date" value={endDate} min={startDate} onChange={(e) => setEndDate(e.target.value)} required />
          </div>
          <Fieldset legend="When you're free" hint={`Local time in ${timezone.replace(/_/g, " ")}. Your exact times stay private; the agent only learns whether a group overlaps.`}>
            <ul className="flex flex-col gap-3">
              {windows.map((w, i) => (
                <li key={i} className="grid grid-cols-[1fr_auto] items-end gap-2 rounded-2xl bg-raised p-3 sm:grid-cols-[1.3fr_1fr_1fr_auto]">
                  <div className="col-span-2 sm:col-span-1"><TextField label="Day" type="date" min={startDate} max={endDate} value={w.date} onChange={(e) => setWindow(i, { date: e.target.value })} required /></div>
                  <div className="col-span-2 grid grid-cols-2 gap-2 sm:col-span-2">
                    <TextField label="From" type="time" value={w.from} onChange={(e) => setWindow(i, { from: e.target.value })} required />
                    <TextField label="Until" type="time" value={w.to} onChange={(e) => setWindow(i, { to: e.target.value })} required />
                  </div>
                  <button type="button" onClick={() => setWindows((ws) => ws.filter((_, j) => j !== i))} disabled={windows.length === 1}
                    aria-label="Remove this time" className="press col-start-2 row-start-1 grid size-11 place-items-center rounded-full text-muted hover:bg-sunk disabled:opacity-40 sm:col-start-auto sm:row-start-auto">
                    <Trash2 className="size-4" aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
            <div>
              <Button type="button" variant="ghost" size="sm" icon={<Plus className="size-4" aria-hidden />}
                onClick={() => setWindows((ws) => [...ws, { date: ws.at(-1)?.date ?? startDate, from: "17:00", to: "21:00" }])}>Add another time</Button>
            </div>
          </Fieldset>
        </Panel>

        <Panel className="flex flex-col gap-5 p-5 sm:p-6">
          <Fieldset legend="Interests" hint="Broad tags only. They help explain why someone might be a good fit.">
            <div className="flex flex-wrap gap-2">
              {[...new Set([...INTEREST_SUGGESTIONS, ...interests])].map((t) => <Chip key={t} selected={interests.includes(t)} onClick={() => toggleInterest(t)}>{t}</Chip>)}
            </div>
            <div className="flex gap-2">
              <input aria-label="Add your own interest" value={custom} onChange={(e) => setCustom(e.target.value)} maxLength={30} placeholder="Add your own"
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); if (custom.trim()) { toggleInterest(custom.trim().toLowerCase()); setCustom(""); } } }}
                className="min-h-11 flex-1 rounded-xl border border-line bg-surface px-3.5 outline-none focus:border-violet" />
              <Button type="button" variant="secondary" onClick={() => { if (custom.trim()) { toggleInterest(custom.trim().toLowerCase()); setCustom(""); } }}>Add</Button>
            </div>
          </Fieldset>
          <div className="grid gap-4 sm:grid-cols-2">
            <SelectField label="Looking for" value={intent} onChange={(e) => setIntent(e.target.value)} options={INTENTS} />
            <Fieldset legend="Group size (including you)">
              <div className="flex gap-2">
                {([[2, 2], [2, 3], [3, 4], [4, 4]] as [number, number][]).map(([a, b]) => (
                  <Chip key={`${a}-${b}`} selected={size[0] === a && size[1] === b} onClick={() => setSize([a, b])}><span className="num">{a === b ? a : `${a}–${b}`}</span></Chip>
                ))}
              </div>
            </Fieldset>
          </div>
          <Switch checked={groupOnly} onChange={setGroupOnly} label="Group meetups only" description="No 1:1 meetups with people you haven't met. Recommended." />
          <TextArea label="Public-safe preview" optional rows={2} maxLength={200} value={preview} onChange={(e) => setPreview(e.target.value)}
            placeholder="Conference-goer, into food and walking tours." hint="The only text an eligible match could see before accepting. No dates, places or contact details." />
        </Panel>

        <Panel className="flex flex-col gap-4 p-5 sm:p-6">
          <Fieldset legend="Discovery">
            {(["private_browse", "mutual_discovery"] as DiscoveryMode[]).map((m) => (
              <label key={m} className={cx("flex cursor-pointer gap-3 rounded-2xl border p-4 transition-colors", mode === m ? "border-ink bg-raised" : "border-line hover:border-control")}>
                <input type="radio" name="discovery" value={m} checked={mode === m} onChange={() => setMode(m)} className="mt-1 size-4 accent-[var(--color-ink)]" />
                <span><span className="block font-medium">{DISCOVERY[m].label}{m === "private_browse" && <span className="font-normal text-muted"> · default</span>}</span>
                  <span className="block text-[13.5px] text-muted">{DISCOVERY[m].help}</span></span>
              </label>
            ))}
          </Fieldset>
          <label className="flex cursor-pointer gap-3 rounded-2xl bg-violet-soft/70 p-4">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-1 size-4 shrink-0 accent-[var(--color-violet)]" />
            <span>
              <span className="block font-medium">Let Gather Agent process this plan with AI</span>
              <span className="block text-[13.5px] text-ink/80">
                Minimized plan details (activity, city, dates, interests, your goal text) are sent to Meta's Muse Spark model to search and explain matches.
                Your exact times, email and identity documents are never sent. You can turn this off anytime.
              </span>
            </span>
          </label>
        </Panel>

        {problem && <p role="alert" className="text-[14px] text-danger">{problem}</p>}
        <InlineError error={error} />
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" size="lg" loading={busy} icon={<ShieldCheck className="size-4" aria-hidden />}>Save private plan</Button>
          <span className="text-[13.5px] text-muted">{consent ? "Next: ask Gather Agent to find your people." : "Your agent won't run until you allow AI processing."}</span>
        </div>
      </form>
    </AppShell>
  );
}
