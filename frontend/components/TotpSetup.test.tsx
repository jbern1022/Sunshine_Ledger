import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TotpSetup, { groupKey } from "./TotpSetup";
import * as acct from "@/lib/account";

vi.mock("@/lib/account", () => ({ startTotpSetup: vi.fn(), finishTotpSetup: vi.fn() }));
vi.mock("qrcode", () => ({ default: { toDataURL: vi.fn().mockResolvedValue("data:image/png;base64,QR") } }));
const m = vi.mocked(acct);

beforeEach(() => {
  m.startTotpSetup.mockReset();
  m.finishTotpSetup.mockReset();
});

async function toScan(user: ReturnType<typeof userEvent.setup>) {
  m.startTotpSetup.mockResolvedValue({ ok: true, secret: "JBSWY3DPEHPK3PXP", uri: "otpauth://totp/x?secret=JBSWY3DPEHPK3PXP" });
  await user.click(screen.getByRole("button", { name: "Set up an authenticator app" }));
  await user.type(screen.getByLabelText("Your password (to confirm it's you)"), "pw-1");
  await user.click(screen.getByRole("button", { name: "Next" }));
}

describe("TotpSetup", () => {
  it("re-checks the password, shows the QR and key, proves a code, then signs out", async () => {
    const onSignedOut = vi.fn();
    const user = userEvent.setup();
    render(<TotpSetup onSignedOut={onSignedOut} />);
    await toScan(user);
    expect(m.startTotpSetup).toHaveBeenCalledWith("pw-1");
    expect(await screen.findByAltText("QR code to add Sunshine Ledger to an authenticator app")).toHaveAttribute("src", "data:image/png;base64,QR");
    expect(screen.getByLabelText("Setup key")).toHaveTextContent("JBSW Y3DP EHPK 3PXP");
    m.finishTotpSetup.mockResolvedValue({ ok: true });
    await user.type(screen.getByLabelText("The 6-digit code the app shows now"), "123456");
    await user.type(screen.getByLabelText("Your password (to confirm it's you)"), "pw-1");
    await user.click(screen.getByRole("button", { name: "Turn it on" }));
    expect(m.finishTotpSetup).toHaveBeenCalledWith("pw-1", "123456");
    expect(onSignedOut).toHaveBeenCalled();
  });

  it("a wrong code turns nothing on and clears the password and code", async () => {
    const onSignedOut = vi.fn();
    const user = userEvent.setup();
    render(<TotpSetup onSignedOut={onSignedOut} />);
    await toScan(user);
    m.finishTotpSetup.mockResolvedValue({ ok: false, code: "invalid_credentials" });
    await user.type(await screen.findByLabelText("The 6-digit code the app shows now"), "000000");
    await user.type(screen.getByLabelText("Your password (to confirm it's you)"), "pw-1");
    await user.click(screen.getByRole("button", { name: "Turn it on" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That didn't work.");
    expect(onSignedOut).not.toHaveBeenCalled();
    expect(screen.getByLabelText("The 6-digit code the app shows now")).toHaveValue("");
    expect(screen.getByLabelText("Your password (to confirm it's you)")).toHaveValue("");
  });

  it("says so when the account already has an authenticator", async () => {
    m.startTotpSetup.mockResolvedValue({ ok: false, code: "mfa_already_enabled" });
    const user = userEvent.setup();
    render(<TotpSetup onSignedOut={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Set up an authenticator app" }));
    await user.type(screen.getByLabelText("Your password (to confirm it's you)"), "pw-1");
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This account already uses an authenticator app.");
  });

  it("groups the key in fours for typing", () => {
    expect(groupKey("ABCDEFGHIJ")).toBe("ABCD EFGH IJ");
  });
});
