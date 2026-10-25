import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { AppShell } from "../components/AppShell";
import { GatherChat } from "../components/GatherChat";
import { VenueTime } from "../components/SafeMeet";
import { ErrorState, LoadingBlock, Panel } from "../components/ui";
import { ApiError } from "../lib/api";
import { useProposal } from "../lib/hooks";
import { NotAvailable } from "./ProposalPage";

export function Room() {
  const { proposalId = "" } = useParams();
  const q = useProposal(proposalId, 3000);
  if (q.isPending) return <AppShell><LoadingBlock label="Loading Gather Room" /></AppShell>;
  if (q.isError) return <AppShell>{q.error instanceof ApiError && q.error.status === 404 ? <NotAvailable /> : <ErrorState error={q.error} what="this room" />}</AppShell>;
  const p = q.data;
  return <AppShell chatAside aside={p.status === "confirmed" ? <GatherChat proposal={p} /> : undefined}>
    <Link to={`/proposals/${p.id}`} className="mb-4 inline-flex min-h-11 items-center gap-1.5 text-[14px] text-muted hover:text-ink"><ArrowLeft className="size-4" aria-hidden /> Meetup details</Link>
    <h1 className="page-title">Your group, together.</h1>
    <p className="mt-2 mb-6 text-muted">{p.activity_title}</p>
    {p.status === "confirmed" ? <><Panel className="p-5"><VenueTime p={p} /></Panel><div className="mt-6 xl:hidden"><GatherChat proposal={p} /></div></>
      : <Panel className="p-5"><p>Chat opens once everyone has confirmed the final time, place and group.</p></Panel>}
  </AppShell>;
}
