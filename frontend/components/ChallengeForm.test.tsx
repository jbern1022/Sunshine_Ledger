import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FlagThis } from "./ChallengeForm";
import * as api from "@/lib/api";

vi.mock("@/lib/api", () => ({ submitFlag: vi.fn() }));

describe("FlagThis", () => {
  it("sends the exact block and version being challenged", async () => {
    vi.mocked(api.submitFlag).mockResolvedValueOnce(undefined);
    const user = userEvent.setup();
    render(
      <FlagThis
        billEntityId="b1"
        target={{ object_type: "bill_layer", object_id: "layer-9", object_version: 3 }}
        label="Flag this block"
      />,
    );
    const toggle = screen.getByRole("button", { name: "Flag this block" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    await user.type(screen.getByLabelText(/what is wrong/i), "Says 15 days; Section 1 says 30.");
    await user.click(screen.getByRole("button", { name: /submit report/i }));
    await waitFor(() =>
      expect(api.submitFlag).toHaveBeenCalledWith(
        expect.objectContaining({
          bill_entity_id: "b1", object_type: "bill_layer", object_id: "layer-9", object_version: 3,
          category: "factually_wrong",
        }),
      ),
    );
  });
});
