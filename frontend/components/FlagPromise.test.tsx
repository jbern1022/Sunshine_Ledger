import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import FlagPromise from "./FlagPromise";
import * as api from "@/lib/api";

vi.mock("@/lib/api", () => ({ flagPromise: vi.fn() }));

describe("FlagPromise", () => {
  it("sends the reason for this statement and confirms", async () => {
    vi.mocked(api.flagPromise).mockResolvedValueOnce(undefined);
    const user = userEvent.setup();
    render(<FlagPromise id="p1" />);
    await user.click(screen.getByRole("button", { name: "Flag this statement" }));
    await user.type(screen.getByLabelText(/what is wrong/i), "This is from a guest post.");
    await user.click(screen.getByRole("button", { name: /submit report/i }));
    await waitFor(() => expect(api.flagPromise).toHaveBeenCalledWith("p1", "This is from a guest post."));
    expect(await screen.findByText(/flagged statements are reviewed first/i)).toBeInTheDocument();
  });

  it("says when the report failed", async () => {
    vi.mocked(api.flagPromise).mockRejectedValueOnce(new Error("x"));
    const user = userEvent.setup();
    render(<FlagPromise id="p1" />);
    await user.click(screen.getByRole("button", { name: "Flag this statement" }));
    await user.type(screen.getByLabelText(/what is wrong/i), "wrong person here");
    await user.click(screen.getByRole("button", { name: /submit report/i }));
    expect(await screen.findByText(/couldn.t be sent/)).toBeInTheDocument();
  });
});
