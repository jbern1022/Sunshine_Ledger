import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("@/lib/account", () => ({
  ACCOUNTS_ENABLED: true, getMe: vi.fn(), getWatchlist: vi.fn(), addWatch: vi.fn(), removeWatch: vi.fn(),
}));
import FollowButton from "./FollowButton";
import * as acct from "@/lib/account";

const m = vi.mocked(acct);
const me = { id: "u", email: "a@example.org", second_factor_required: false, restricted: false, factors: ["pwd"] };
beforeEach(() => Object.values(m).forEach((f) => typeof f === "function" && (f as ReturnType<typeof vi.fn>).mockReset()));

describe("FollowButton", () => {
  it("sends a visitor to sign in", async () => {
    m.getMe.mockResolvedValue(null);
    render(<FollowButton kind="bill" target="b1" label="HB 1" />);
    expect(await screen.findByRole("link", { name: "Sign in to follow HB 1" })).toHaveAttribute("href", "/account");
  });

  it("follows and unfollows", async () => {
    m.getMe.mockResolvedValue(me);
    m.getWatchlist.mockResolvedValueOnce([]).mockResolvedValueOnce([{ id: "w1", kind: "bill", target: "b1", jurisdiction: null }]);
    m.addWatch.mockResolvedValue({ ok: true });
    m.removeWatch.mockResolvedValue(true);
    const user = userEvent.setup();
    render(<FollowButton kind="bill" target="b1" label="HB 1" />);
    const btn = await screen.findByRole("button", { name: "Follow HB 1" });
    expect(btn).toHaveAttribute("aria-pressed", "false");
    await user.click(btn);
    expect(m.addWatch).toHaveBeenCalledWith("bill", "b1", "");
    const on = await screen.findByRole("button", { name: "Following HB 1" });
    expect(on).toHaveAttribute("aria-pressed", "true");
    await user.click(on);
    await waitFor(() => expect(screen.getByRole("button", { name: "Follow HB 1" })).toBeInTheDocument());
    expect(m.removeWatch).toHaveBeenCalledWith("w1");
  });

  it("starts as following when the list already has it, and reports a failed save", async () => {
    m.getMe.mockResolvedValue(me);
    m.getWatchlist.mockResolvedValue([{ id: "w9", kind: "bill", target: "b1", jurisdiction: null }]);
    m.removeWatch.mockResolvedValue(false);
    const user = userEvent.setup();
    render(<FollowButton kind="bill" target="b1" label="HB 1" />);
    await user.click(await screen.findByRole("button", { name: "Following HB 1" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("didn't save");
  });
});
