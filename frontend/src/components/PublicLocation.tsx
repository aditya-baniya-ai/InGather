import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { MapPin } from "lucide-react";
import { api, type Plan } from "../lib/api";
import { keys, useAction } from "../lib/hooks";
import { Button, InlineError, TextField } from "./ui";

/** The event anchor stays owner-only. Only the chosen meetup venue is disclosed to accepted members. */
export function PublicLocation({ plan }: { plan: Plan }) {
  const [location, setLocation] = useState(plan.public_location ?? "");
  const qc = useQueryClient();
  const save = useAction((value: string) => api.updatePlan(plan.id, { public_location: value }), [keys.plans], p => {
    qc.setQueryData(keys.plan(p.id), p);
    qc.removeQueries({ queryKey: ["nearby", p.id] });
  });
  const changed = location.trim() !== (plan.public_location ?? "");
  return <div className="mt-5 rounded-2xl border border-violet/20 bg-violet-soft/40 p-4">
    <TextField label={<span className="inline-flex items-center gap-2"><MapPin className="size-4 text-violet-ink" aria-hidden />Conference or public event location</span>} value={location} onChange={e => setLocation(e.target.value)} maxLength={200} placeholder="Pennsylvania Convention Center, 1101 Arch St" optional hint="Use a public venue or street address, never your hotel or home. Nearby search sends this location and city to OpenStreetMap. Changes apply to your next search, not an agreed meetup." />
    {changed && <Button className="mt-3" size="sm" loading={save.isPending} onClick={() => save.mutate(location.trim())}>Save event location</Button>}
    {save.isSuccess && !changed && <p role="status" className="mt-2 text-[13px] text-emerald-ink">Event location saved.</p>}
    <InlineError error={save.error} />
  </div>;
}
