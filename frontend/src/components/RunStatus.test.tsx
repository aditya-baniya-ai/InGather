import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { Run } from "../lib/api";
import { RunStatus } from "./RunStatus";

const run = (status: Run["status"], error: string | null = null) => ({ id: "r", status, error, events: [] } as unknown as Run);
const show = (r: Run, onRetry?: () => void) => render(<MemoryRouter><RunStatus run={r} onRetry={onRetry} /></MemoryRouter>);

describe("RunStatus", () => {
  it("shows a plain progress message while searching, with no technical steps", () => {
    show(run("running"));
    expect(screen.getByRole("status")).toHaveTextContent("Finding people who share your plans");
    expect(screen.queryByText(/matcher|find_eligible/i)).toBeNull();
  });
  it("shows nothing once the search is done", () => {
    const { container } = show(run("completed"));
    expect(container).toBeEmptyDOMElement();
  });
  it("offers Try again when a search stops", () => {
    const retry = vi.fn();
    show(run("failed", "no_suitable_group"), retry);
    screen.getByRole("button", { name: /Try again/ }).click();
    expect(retry).toHaveBeenCalled();
  });
});
