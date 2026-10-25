import { useRef, useState, type FormEvent, type ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Lock, Plus, ShieldCheck, Sparkles, Trash2 } from "lucide-react";
import { AppShell } from "../components/AppShell";
import { VoiceButton } from "../components/VoiceButton";
import { AiMark, Button, Chip, cx, InlineError, Panel, SelectField, Switch, Tabs, TextArea, TextField } from "../components/ui";
import { api, ApiError, type DiscoveryMode, type PlanDraft } from "../lib/api";
import { draftToForm, MISSING_COPY, type FormKey, type PlanForm } from "../lib/forms";
import { keys, useAction } from "../lib/hooks";
import { browserTimeZone, TIMEZONES, windowsToUtc, type LocalWindow } from "../lib/time";
import { ACTIVITIES, DISCOVERY, INTENTS, INTEREST_SUGGESTIONS } from "../lib/vocab";

function Fieldset({ legend, children, hint }: { legend: ReactNode; children: ReactNode; hint?: string }) {
  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="mb-2 text-[14px] font-medium">{legend}</legend>
      {hint && <p className="-mt-2 text-[13px] text-muted">{hint}</p>}
      {children}
    </fieldset>
  );
}

/** "Describe it": free text (typed or spoken) -> Intake agent draft. Never saves. */
function IntakePanel({ initial, aiOff, onDraft, onUnavailable }: { initial: string; aiOff: boolean; onDraft: (d: PlanDraft) => void; onUnavailable: (text: string) => void }) {
  const [text, setText] = useState(initial);
  const draft = useAction((t: string) => api.draftPlan(t, browserTimeZone()), [], onDraft);
  const fill = () => draft.mutate(text.trim(), { onError: (e) => { if (e instanceof ApiError && e.status === 503) onUnavailable(text.trim()); } });
  return (
    <Panel className="flex flex-col gap-4 p-5 sm:p-6">
      <TextArea label="Describe your plan" rows={6} value={text} onChange={(e) => setText(e.target.value)} maxLength={2000}
        placeholder="I'm at a conference in Philadelphia Jan 17–19, free after 5 PM. Up for food and a museum with 2–3 people."
        hint="Where, when you're free, what you'd enjoy and how many people. Your text goes to Meta's Muse Spark to draft the form below; nothing is saved until you review it." />
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" variant="agent" size="lg" onClick={fill} loading={draft.isPending} disabled={aiOff || text.trim().length === 0}
          icon={<Sparkles className="size-4" aria-hidden />}>{draft.isPending ? "Drafting…" : "Fill with AI"}</Button>
        <VoiceButton onText={(t) => setText((x) => (x ? `${x} ${t}` : t))} />
      </div>
      {aiOff ? <p className="text-[14px] text-muted">The Intake agent is unavailable right now. Use Fill manually instead.</p> : <InlineError error={draft.error} />}
    </Panel>
  );
}

const nextWeek = () => { const d = new Date(Date.now() + 7 * 864e5); return d.toISOString().slice(0, 10); };

export function CreatePlan() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const tz0 = browserTimeZone();
  const [entry, setEntry] = useState<"describe" | "manual">("describe");
  const [form, setForm] = useState<PlanForm>(() => ({
    activity: params.get("activity") ?? "conference", title: "", goal: params.get("goal") ?? "", city: "", timezone: TIMEZONES.includes(tz0) ? tz0 : "America/Chicago",
    startDate: nextWeek(), endDate: nextWeek(), windows: [{ date: nextWeek(), from: "17:00", to: "21:00" }],
    interests: [], intent: "friends", size: [3, 4], groupOnly: true,
  }));
  const { activity, title, goal, city, timezone, startDate, endDate, windows, interests, intent, size, groupOnly } = form;
  const [filled, setFilled] = useState<Set<FormKey>>(new Set());
  const [draft, setDraft] = useState<PlanDraft | null>(null);
  const [aiOff, setAiOff] = useState(false);
  const [custom, setCustom] = useState("");
  const [publicLocation, setPublicLocation] = useState("");
  const [preview, setPreview] = useState("");
  const [mode, setMode] = useState<DiscoveryMode>("private_browse");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const formRef = useRef<HTMLFormElement>(null);

  /** User edits clear the "filled by AI" marker: the value is now theirs. */
  const set = (patch: Partial<PlanForm>) => {
    setForm((f) => ({ ...f, ...patch }));
    setFilled((s) => new Set([...s].filter((k) => !(k in patch))));
  };
  const ai = (k: FormKey) => (filled.has(k) ? <AiMark /> : null);

  const toggleInterest = (t: string) => set({ interests: interests.includes(t) ? interests.filter((x) => x !== t) : [...interests, t].slice(0, 10) });
  const addCustom = () => { if (custom.trim()) { toggleInterest(custom.trim().toLowerCase()); setCustom(""); } };
  const setWindow = (i: number, patch: Partial<LocalWindow>) => set({ windows: windows.map((w, j) => (j === i ? { ...w, ...patch } : w)) });
  const changeStart = (d: string) => set({ startDate: d, endDate: endDate < d ? d : endDate, windows: windows.map((w) => (w.date < d ? { ...w, date: d } : w)) });

  const applyDraft = (d: PlanDraft) => {
    const { patch, filled: keysFilled } = draftToForm(d, form);
    setForm((f) => ({ ...f, ...patch }));
    setFilled(new Set(keysFilled));
    setDraft(d);
    if (d.public_location) setPublicLocation(d.public_location);
    const smooth = !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    requestAnimationFrame(() => formRef.current?.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "start" }));
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
        activity_type: activity, title: title.trim(), goal_text: goal.trim(), city: city.trim(), timezone, public_location: publicLocation.trim() || null,
        start_date: startDate, end_date: endDate, intent, interests, group_min: size[0], group_max: size[1],
        group_only: groupOnly, preview_text: preview.trim() || null, windows: windowsToUtc(windows, timezone),
      });
      const saved = mode !== plan.discovery_mode || consent ? await api.setDiscovery(plan.id, mode, consent) : plan;
      qc.setQueryData(keys.plan(saved.id), saved);
      qc.invalidateQueries({ queryKey: keys.plans });
      navigate(`/plans/${saved.id}`, { state: { created: true } });
    } catch (err) { setError(err); } finally { setBusy(false); }
  };

  const sizes = ([[2, 2], [2, 3], [3, 4], [4, 4]] as [number, number][]);
  if (!sizes.some(([a, b]) => a === size[0] && b === size[1])) sizes.push(size);
  const missing = [...new Set(draft?.missing.map((m) => MISSING_COPY[m] ?? m.replace(/_/g, " ")) ?? [])];

  return (
    <AppShell>
      <header className="mb-6">
        <h1 className="page-title">New <span className="ig-text">private</span> plan</h1>
        <p className="mt-1 flex items-center gap-1.5 text-[15px] text-muted"><Lock className="size-4" aria-hidden /> Your private itinerary is not public.</p>
      </header>

      <div className="mb-5">
        <Tabs idBase="entry" label="How to create your plan" value={entry} onChange={setEntry}
          options={[{ value: "describe", label: <><Sparkles className="size-4" aria-hidden /> Describe it</> }, { value: "manual", label: "Fill manually" }]} />
      </div>

      <div role="tabpanel" id="entry-panel" aria-labelledby={`entry-tab-${entry}`} className="flex flex-col gap-5">
      <div hidden={entry !== "describe"}>
        <IntakePanel initial={params.get("goal") ?? ""} aiOff={aiOff} onDraft={applyDraft}
          onUnavailable={(text) => { setAiOff(true); setEntry("manual"); if (!goal.trim()) set({ goal: text }); }} />
      </div>
      {entry === "manual" && aiOff && <p role="status" className="rounded-2xl bg-raised px-4 py-3 text-[14.5px]">The Intake agent is unavailable right now, so fill in the form yourself.</p>}

      {(entry === "manual" || draft) && (
      <form ref={formRef} onSubmit={submit} className="flex scroll-mt-20 flex-col gap-5">
        {entry === "describe" && draft && (
          <Panel as="aside" className="rise border-violet/20 bg-violet-soft/60 p-5 text-[14.5px]">
            <p className="flex items-center gap-2 font-medium text-violet-ink"><Sparkles className="size-4" aria-hidden /> Drafted by Intake agent. Review every field; nothing is saved yet.</p>
            {draft.notes && <p className="mt-1.5">{draft.notes}</p>}
            {missing.length > 0 && (
              <div className="mt-3">
                <p className="font-medium">Still needed from you</p>
                <ul className="mt-1 list-disc pl-5">{missing.map((m) => <li key={m}>{m}</li>)}</ul>
              </div>
            )}
          </Panel>
        )}
        <Panel className="flex flex-col gap-5 p-5 sm:p-6">
          <Fieldset legend={<>What kind of plan?{ai("activity")}</>}>
            <div className="flex flex-wrap gap-2">
              {ACTIVITIES.map((a) => <Chip key={a.value} selected={activity === a.value} onClick={() => set({ activity: a.value })}>{a.label}</Chip>)}
            </div>
          </Fieldset>
          <TextField label={<>Title{ai("title")}</>} value={title} onChange={(e) => set({ title: e.target.value })} required maxLength={120} placeholder="Philly tech conference, evenings free" />
          <div className="flex flex-col gap-2">
            <TextArea label={<>Your goal, in your words{ai("goal")}</>} rows={4} value={goal} onChange={(e) => set({ goal: e.target.value })} required maxLength={2000}
              placeholder="I'm in Philadelphia for a tech conference Jan 17–19 and would love to explore after 5 PM."
              hint="Private. Only you and, with your consent, your Gather Agent read this." />
            {entry === "manual" && <VoiceButton onText={(t) => set({ goal: goal ? `${goal} ${t}` : t })} />}
          </div>
        </Panel>

        <Panel className="flex flex-col gap-5 p-5 sm:p-6">
          <div className="grid gap-4 sm:grid-cols-2">
            <TextField label={<>City or region{ai("city")}</>} value={city} onChange={(e) => set({ city: e.target.value })} required maxLength={80} placeholder="Philadelphia" />
            <SelectField label={<>Time zone{ai("timezone")}</>} value={timezone} onChange={(e) => set({ timezone: e.target.value })}
              options={[...new Set([...TIMEZONES, timezone])].map((z) => ({ value: z, label: z.replace(/_/g, " ") }))} />
            <TextField label={<>From{ai("startDate")}</>} type="date" value={startDate} onChange={(e) => changeStart(e.target.value)} required />
            <TextField label={<>To{ai("endDate")}</>} type="date" value={endDate} min={startDate} onChange={(e) => set({ endDate: e.target.value })} required />
          </div>
          <TextField label="Conference or public event location" optional value={publicLocation} onChange={e => setPublicLocation(e.target.value)} maxLength={200} placeholder="Pennsylvania Convention Center, 1101 Arch St" hint="A public venue or street address helps find nearby cafés and restaurants. Never use your hotel or home. Nearby lookup sends only this location and city to OpenStreetMap." />
          <Fieldset legend={<>When you're free{ai("windows")}</>} hint={`Local time in ${timezone.replace(/_/g, " ")}. Your exact times stay private; the agent only learns whether a group overlaps.`}>
            <ul className="flex flex-col gap-3">
              {windows.map((w, i) => (
                <li key={i} className="grid grid-cols-[1fr_auto] items-end gap-2 rounded-2xl bg-raised p-3 sm:grid-cols-[1.3fr_1fr_1fr_auto]">
                  <div className="col-span-2 sm:col-span-1"><TextField label="Day" type="date" min={startDate} max={endDate} value={w.date} onChange={(e) => setWindow(i, { date: e.target.value })} required /></div>
                  <div className="col-span-2 grid grid-cols-2 gap-2 sm:col-span-2">
                    <TextField label="From" type="time" value={w.from} onChange={(e) => setWindow(i, { from: e.target.value })} required />
                    <TextField label="Until" type="time" value={w.to} onChange={(e) => setWindow(i, { to: e.target.value })} required />
                  </div>
                  <button type="button" onClick={() => set({ windows: windows.filter((_, j) => j !== i) })} disabled={windows.length === 1}
                    aria-label="Remove this time" className="press col-start-2 row-start-1 grid size-11 place-items-center rounded-full text-muted hover:bg-sunk disabled:opacity-40 sm:col-start-auto sm:row-start-auto">
                    <Trash2 className="size-4" aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
            <div>
              <Button type="button" variant="ghost" size="sm" icon={<Plus className="size-4" aria-hidden />}
                onClick={() => set({ windows: [...windows, { date: windows.at(-1)?.date ?? startDate, from: "17:00", to: "21:00" }] })}>Add another time</Button>
            </div>
          </Fieldset>
        </Panel>

        <Panel className="flex flex-col gap-5 p-5 sm:p-6">
          <Fieldset legend={<>Interests{ai("interests")}</>} hint="Broad tags only. They help explain why someone might be a good fit.">
            <div className="flex flex-wrap gap-2">
              {[...new Set([...INTEREST_SUGGESTIONS, ...interests])].map((t) => <Chip key={t} selected={interests.includes(t)} onClick={() => toggleInterest(t)}>{t}</Chip>)}
            </div>
            <div className="flex gap-2">
              <input aria-label="Add your own interest" value={custom} onChange={(e) => setCustom(e.target.value)} maxLength={30} placeholder="Add your own"
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addCustom(); } }}
                className="min-h-11 flex-1 rounded-xl border border-line bg-surface px-3.5 outline-none focus:border-violet" />
              <Button type="button" variant="secondary" onClick={addCustom}>Add</Button>
            </div>
          </Fieldset>
          <div className="grid gap-4 sm:grid-cols-2">
            <SelectField label={<>Looking for{ai("intent")}</>} value={intent} onChange={(e) => set({ intent: e.target.value })} options={INTENTS} />
            <Fieldset legend={<>Group size (including you){ai("size")}</>}>
              <div className="flex flex-wrap gap-2">
                {sizes.map(([a, b]) => (
                  <Chip key={`${a}-${b}`} selected={size[0] === a && size[1] === b} onClick={() => set({ size: [a, b] })}><span className="num">{a === b ? a : `${a}–${b}`}</span></Chip>
                ))}
              </div>
            </Fieldset>
          </div>
          <Switch checked={groupOnly} onChange={(v) => set({ groupOnly: v })} label={<>Group meetups only{ai("groupOnly")}</>} description="No 1:1 meetups with people you haven't met. Recommended." />
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
                Minimized plan details (activity, city, public event location if provided, dates, interests, your goal text) are sent to Meta's Muse Spark model to search and explain matches.
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
      )}
      </div>
    </AppShell>
  );
}
