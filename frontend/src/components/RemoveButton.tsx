import { useState } from "react";
import type { QueryKey } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useAction } from "../lib/hooks";
import { Button, Dialog, InlineError } from "./ui";

/** Small trash button + confirmation dialog for removing a plan, a group or a chat from your account. */
export function RemoveButton({ label, title, body, confirm = "Remove", onRemove, invalidate }: {
  label: string; title: string; body: string; confirm?: string; onRemove: () => Promise<unknown>; invalidate: QueryKey[];
}) {
  const [open, setOpen] = useState(false);
  const remove = useAction(onRemove, invalidate, () => setOpen(false));
  return (
    <>
      <button type="button" aria-label={label} title={label}
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); setOpen(true); }}
        className="press grid size-11 shrink-0 place-items-center rounded-full bg-surface/95 text-muted shadow-sm transition-colors hover:text-danger">
        <Trash2 className="size-[18px]" aria-hidden />
      </button>
      <Dialog open={open} onClose={() => setOpen(false)} title={title}
        footer={<><Button variant="ghost" onClick={() => setOpen(false)}>Keep it</Button><Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate(undefined)}>{confirm}</Button></>}>
        <p>{body}</p>
        <InlineError error={remove.error} />
      </Dialog>
    </>
  );
}
