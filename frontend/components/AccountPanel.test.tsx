import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AccountPanel from "./AccountPanel";
import * as acct from "@/lib/account";

vi.mock("@/lib/account", () => ({
  getMe: vi.fn(), getWatchlist: vi.fn(), signIn: vi.fn(), answerTotp: vi.fn(), signOut: vi.fn(), signOutEverywhere: vi.fn(),
  deleteAccount: vi.fn(), exportData: vi.fn(), removeWatch: vi.fn(),
}));
const m = vi.mocked(acct);
const me = { id: "u1", email: "a@example.org", second_factor_required: false, restricted: false, factors: ["pwd"] };

beforeEach(() => {
  Object.values(m).forEach((f) => (f as ReturnType<typeof vi.fn>).mockReset());
  m.getWatchlist.mockResolvedValue([]);
});

describe("AccountPanel", () => {
  it("shows the sign-in form to a visitor and signs in, then shows the account", async () => {
    m.getMe.mockResolvedValueOnce(null).mockResolvedValueOnce(me);
    m.signIn.mockResolvedValue({ kind: "signed_in" });
    const user = userEvent.setup();
    render(<AccountPanel />);
    await user.type(await screen.findByLabelText("Email address"), "a@example.org");
    await user.type(screen.getByLabelText("Password"), "pw-1");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(m.signIn).toHaveBeenCalledWith("a@example.org", "pw-1");
    expect(await screen.findByText("Signed in as a@example.org.")).toBeInTheDocument();
    expect(screen.getByText("You aren't following anything yet.")).toBeInTheDocument();
  });

  it("walks the second step, clears the password, and restarts after a wrong code", async () => {
    m.getMe.mockResolvedValue(null);
    m.signIn.mockResolvedValue({ kind: "totp", challengeToken: "c1" });
    m.answerTotp.mockResolvedValue({ kind: "failed", code: "invalid_credentials" });
    const user = userEvent.setup();
    render(<AccountPanel />);
    await user.type(await screen.findByLabelText("Email address"), "a@example.org");
    await user.type(screen.getByLabelText("Password"), "pw-1");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.type(await screen.findByLabelText("Code from your authenticator app"), "123456");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(m.answerTotp).toHaveBeenCalledWith("c1", "123456");
    expect(await screen.findByRole("alert")).toHaveTextContent("That didn't work");
    expect(await screen.findByLabelText("Password")).toHaveValue(""); // back to the first step, nothing retained
  });

  it("says the same thing for every credential failure and a specific thing for a held second factor", async () => {
    m.getMe.mockResolvedValue(null);
    m.signIn.mockResolvedValueOnce({ kind: "failed", code: "invalid_credentials" }).mockResolvedValueOnce({ kind: "failed", code: "mfa_required" });
    const user = userEvent.setup();
    render(<AccountPanel />);
    await user.type(await screen.findByLabelText("Email address"), "a@example.org");
    await user.type(screen.getByLabelText("Password"), "x");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Check your email address and password");
    await user.type(screen.getByLabelText("Password"), "y");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("uses a second step"));
  });

  it("signs out, and deleting needs an explicit confirmation", async () => {
    m.getMe.mockResolvedValue(me);
    m.signOut.mockResolvedValue({ ok: true });
    m.deleteAccount.mockResolvedValue({ ok: false, code: "reauth_required" });
    const user = userEvent.setup();
    render(<AccountPanel />);
    await user.click(await screen.findByRole("button", { name: "Delete my account" }));
    expect(m.deleteAccount).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Yes, delete everything" }));
    expect(await screen.findByRole("status")).toHaveTextContent("sign in again");
    await user.click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByLabelText("Email address")).toBeInTheDocument();
  });

  it("a restricted recovery session sees no watchlist and no delete", async () => {
    m.getMe.mockResolvedValue({ ...me, restricted: true });
    render(<AccountPanel />);
    expect(await screen.findByText(/can only enroll a new second factor/)).toBeInTheDocument();
    expect(screen.queryByText("What you follow")).toBeNull();
    expect(screen.queryByRole("button", { name: "Delete my account" })).toBeNull();
    expect(m.getWatchlist).not.toHaveBeenCalled();
  });

  it("unfollow removes the row", async () => {
    m.getMe.mockResolvedValue(me);
    m.getWatchlist.mockResolvedValue([{ id: "w1", kind: "bill", target: "abc", jurisdiction: null }]);
    m.removeWatch.mockResolvedValue(true);
    const user = userEvent.setup();
    render(<AccountPanel />);
    await user.click(await screen.findByRole("button", { name: "Stop following" }));
    await waitFor(() => expect(screen.getByText("You aren't following anything yet.")).toBeInTheDocument());
  });
});
