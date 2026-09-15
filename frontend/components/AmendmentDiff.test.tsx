import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AmendmentDiff from "./AmendmentDiff";

describe("AmendmentDiff", () => {
  it("starts collapsed", () => {
    render(<AmendmentDiff baseText="The quick brown fox" amendedText="The quick red fox" />);
    expect(screen.getByRole("button", { name: "View changes" })).toBeInTheDocument();
    expect(screen.queryByText(/diffed against/i)).not.toBeInTheDocument();
  });

  it("expands to show the diff, marking removed and added words", async () => {
    const user = userEvent.setup();
    render(<AmendmentDiff baseText="The quick brown fox" amendedText="The quick red fox" />);

    await user.click(screen.getByRole("button", { name: "View changes" }));

    expect(screen.getByRole("button", { name: "Hide changes" })).toBeInTheDocument();
    expect(screen.getByText("brown")).toHaveClass("line-through");
    expect(screen.getByText("red")).toHaveClass("bg-emerald-100");
  });

  it("collapses again on a second click", async () => {
    const user = userEvent.setup();
    render(<AmendmentDiff baseText="a b c" amendedText="a x c" />);

    await user.click(screen.getByRole("button", { name: "View changes" }));
    await user.click(screen.getByRole("button", { name: "Hide changes" }));

    expect(screen.getByRole("button", { name: "View changes" })).toBeInTheDocument();
    expect(screen.queryByText(/diffed against/i)).not.toBeInTheDocument();
  });
});
