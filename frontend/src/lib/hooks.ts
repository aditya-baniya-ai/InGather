import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { api, ApiError, type Proposal, type Run } from "./api";

const noRetryOn4xx = (count: number, err: unknown) =>
  !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 2;

export const keys = {
  plans: ["plans"] as const,
  plan: (id: string) => ["plan", id] as const,
  run: (id: string) => ["run", id] as const,
  proposal: (id: string) => ["proposal", id] as const,
  invitations: ["invitations"] as const,
  messages: (id: string) => ["messages", id] as const,
  blocks: ["blocks"] as const,
  demo: ["demo-accounts"] as const,
  verification: ["verification"] as const,
  feed: ["feed"] as const,
  joinRequests: (id: string) => ["join-requests", id] as const,
};

export const usePlans = () => useQuery({ queryKey: keys.plans, queryFn: api.plans });

export const usePlan = (id: string | undefined, poll?: number) =>
  useQuery({ queryKey: keys.plan(id ?? ""), queryFn: () => api.plan(id!), enabled: !!id, retry: noRetryOn4xx, refetchInterval: poll });

/** Agent run, polled every second while it is running (per contract). */
export const useRun = (id: string | null | undefined) =>
  useQuery({
    queryKey: keys.run(id ?? ""),
    queryFn: () => api.run(id!),
    enabled: !!id,
    retry: noRetryOn4xx,
    refetchInterval: (q) => (q.state.data?.status === "running" ? 1000 : false),
  });

export const useProposal = (id: string | null | undefined, poll: number | false = 4000) =>
  useQuery({ queryKey: keys.proposal(id ?? ""), queryFn: () => api.proposal(id!), enabled: !!id, retry: noRetryOn4xx, refetchInterval: poll });

export const useInvitations = () =>
  useQuery({ queryKey: keys.invitations, queryFn: api.invitations, refetchInterval: 5000 });

export const useMessages = (id: string, enabled: boolean) =>
  useQuery({ queryKey: keys.messages(id), queryFn: () => api.messages(id), enabled, retry: noRetryOn4xx, refetchInterval: 3000 });

/** Home feed in the chosen order; polls every few seconds while a join request is waiting for an answer. */
export const useFeed = (sort: "match" | "soonest" = "match") =>
  useQuery({
    queryKey: [...keys.feed, sort], queryFn: () => api.feed(sort), placeholderData: (prev) => prev,
    refetchInterval: (q) => (q.state.data?.some((i) => i.request_status === "pending") ? 2000 : 30000),
  });

export const useJoinRequests = (id: string | undefined, enabled: boolean) =>
  useQuery({ queryKey: keys.joinRequests(id ?? ""), queryFn: () => api.joinRequests(id!), enabled: !!id && enabled, retry: noRetryOn4xx, refetchInterval: 5000 });

export const useBlocks = () => useQuery({ queryKey: keys.blocks, queryFn: api.blocks });

/** Verification status; `poll` (ms) while waiting for a Stripe webhook. */
export const useVerification = (poll: number | false = false) =>
  useQuery({ queryKey: keys.verification, queryFn: api.verification, retry: noRetryOn4xx, refetchInterval: poll });

export const useDemoAccounts = () =>
  useQuery({ queryKey: keys.demo, queryFn: api.demoAccounts, retry: false, staleTime: Infinity });

/** Mutation that invalidates the given keys on success. */
export function useAction<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>, invalidate: QueryKey[] = [], onSuccess?: (r: TResult) => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (r) => {
      invalidate.forEach((k) => qc.invalidateQueries({ queryKey: k }));
      onSuccess?.(r);
    },
  });
}

/** Store a proposal returned by a mutation straight into the cache. */
export function useSetProposal() {
  const qc = useQueryClient();
  return (p: Proposal) => qc.setQueryData(keys.proposal(p.id), p);
}

/**
 * Tracks which agent run the workspace is following: the plan's latest run, or one the user
 * just started (pass/replan return a new RunOut). When it finishes, refresh plan + proposal.
 */
export function useFollowRun(planId: string, latestRunId: string | null | undefined) {
  const qc = useQueryClient();
  const [runId, setRunId] = useState<string | null>(latestRunId ?? null);
  useEffect(() => { if (latestRunId) setRunId(latestRunId); }, [latestRunId]);
  const run = useRun(runId);
  const status = run.data?.status;
  useEffect(() => {
    if (status && status !== "running") {
      qc.invalidateQueries({ queryKey: keys.plan(planId) });
      if (run.data?.proposal_id) qc.invalidateQueries({ queryKey: keys.proposal(run.data.proposal_id) });
    }
  }, [status, planId, run.data?.proposal_id, qc]);
  const follow = (r: Run) => {
    qc.setQueryData(keys.run(r.id), r);
    setRunId(r.id);
  };
  return { run, follow };
}
