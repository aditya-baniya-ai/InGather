import { useState } from "react";
import { Ban, Flag, LogOut } from "lucide-react";
import { api } from "../lib/api";
import { useAction } from "../lib/hooks";
import { REPORT_REASONS } from "../lib/vocab";
import { Button, Dialog, InlineError, SelectField, TextArea } from "./ui";

interface Props {
  proposalId: string;
  /** Person to block/report (e.g. the organizer). Omit when unknown. */
  person?: { id: string; name: string };
  leaveLabel?: string;
  onLeave?: () => void;
  onBlocked?: () => void;
}

/** Leave / Block / Report: always visible wherever two people could meet. */
export function SafetyActions({ proposalId, person, leaveLabel, onLeave, onBlocked }: Props) {
  const [dialog, setDialog] = useState<"report" | "block" | "leave" | null>(null);
  const [reason, setReason] = useState(REPORT_REASONS[0].value);
  const [details, setDetails] = useState("");
  const [done, setDone] = useState<string | null>(null);

  const report = useAction(() => api.report({ reason, details: details || undefined, proposal_id: proposalId, reported_user_id: person?.id }), [],
    () => { setDialog(null); setDone("Report sent. Our team reviews every report. You can also block this person."); });
  const block = useAction(() => api.block(person!.id), [["blocks"], ["invitations"]],
    () => { setDialog(null); setDone(`${person?.name} is blocked. You won't be matched or invited together.`); onBlocked?.(); });
  const leave = useAction(() => api.leave(proposalId), [["invitations"], ["plans"]], () => { setDialog(null); onLeave?.(); });

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {onLeave && <Button variant="secondary" size="sm" onClick={() => setDialog("leave")} icon={<LogOut className="size-4" aria-hidden />}>{leaveLabel ?? "Leave group"}</Button>}
        {person && <Button variant="secondary" size="sm" onClick={() => setDialog("block")} icon={<Ban className="size-4" aria-hidden />}>Block {person.name}</Button>}
        <Button variant="secondary" size="sm" onClick={() => setDialog("report")} icon={<Flag className="size-4" aria-hidden />}>Report</Button>
      </div>
      {done && <p role="status" className="mt-2 text-[14px] text-emerald-ink">{done}</p>}

      <Dialog open={dialog === "report"} onClose={() => setDialog(null)} title="Report a concern"
        footer={<><Button variant="ghost" onClick={() => setDialog(null)}>Cancel</Button><Button onClick={() => report.mutate(undefined)} loading={report.isPending}>Send report</Button></>}>
        <div className="flex flex-col gap-4">
          <SelectField label="What happened?" value={reason} onChange={(e) => setReason(e.target.value)} options={REPORT_REASONS} />
          <TextArea label="Details" optional rows={3} maxLength={1000} value={details} onChange={(e) => setDetails(e.target.value)} />
          <p className="text-[13.5px] text-muted">If you're in danger, contact local emergency services. InGather doesn't monitor meetups.</p>
          <InlineError error={report.error} />
        </div>
      </Dialog>

      <Dialog open={dialog === "block"} onClose={() => setDialog(null)} title={`Block ${person?.name ?? ""}?`}
        footer={<><Button variant="ghost" onClick={() => setDialog(null)}>Cancel</Button><Button variant="danger" onClick={() => block.mutate(undefined)} loading={block.isPending}>Block</Button></>}>
        <p>They won't be told. You'll both be removed from each other's open proposals and never matched again. You can unblock from Profile.</p>
        <InlineError error={block.error} />
      </Dialog>

      <Dialog open={dialog === "leave"} onClose={() => setDialog(null)} title={leaveLabel ?? "Leave this group?"}
        footer={<><Button variant="ghost" onClick={() => setDialog(null)}>Stay</Button><Button variant="danger" onClick={() => leave.mutate(undefined)} loading={leave.isPending}>{leaveLabel ?? "Leave"}</Button></>}>
        <p>You'll lose access to the group's details and chat right away. Anything already shared can't be unseen by others.</p>
        <InlineError error={leave.error} />
      </Dialog>
    </div>
  );
}
