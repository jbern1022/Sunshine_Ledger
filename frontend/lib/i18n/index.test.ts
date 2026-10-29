import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import { createElement } from "react";

import { DEFAULT_LOCALE, LOCALES, formatNumber, t, tRich, translate } from "./index";

describe("t", () => {
  it("returns the English message", () => {
    expect(t("nav.browse")).toBe("Browse");
    expect(DEFAULT_LOCALE).toBe("en");
    expect(LOCALES).toContain(DEFAULT_LOCALE);
  });

  it("replaces {placeholders} and leaves an unknown one visible", () => {
    expect(t("freshness.ok", { date: "Oct 27", link: "X" })).toBe("State and local bills are checked nightly · last checked Oct 27 · X");
    expect(t("freshness.ok", { date: "Oct 27" })).toContain("{link}");
  });

  it("chooses a plural form by count and formats the number", () => {
    expect(t("coverage.local", { count: 1 })).toBe("1 local government");
    expect(t("coverage.local", { count: 31 })).toBe("31 local governments");
    expect(t("sources.bills", { count: 3900 })).toBe("3,900 bills");
    expect(t("sources.bills", { count: 1 })).toBe("1 bill");
    expect(t("sources.bills", { count: 0 })).toBe("0 bills");
  });

  it("shows the key itself for a key that does not exist", () => {
    expect(translate("en", "no.such.key")).toBe("no.such.key");
  });

  it("formats numbers with the locale's tag", () => {
    expect(formatNumber(1234567)).toBe("1,234,567");
  });
});

describe("tRich", () => {
  it("renders text and nodes in order without a key warning", () => {
    const errors: unknown[] = [];
    const spy = vi.spyOn(console, "error").mockImplementation((...a) => void errors.push(a));
    const link = createElement("a", { href: "/x" }, "About");
    const { container } = render(createElement("p", null, tRich("freshness.failed", { link })));
    spy.mockRestore();
    expect(container.textContent).toBe(
      "We couldn't check how recently the data was updated, so these bills may be out of date · About",
    );
    expect(container.querySelector("a")).toHaveAttribute("href", "/x");
    expect(errors).toEqual([]);
  });

  it("keeps text after the last placeholder", () => {
    const { container } = render(createElement("p", null, tRich("coverage.rest", { local: "31 local governments" })));
    expect(container.textContent).toBe(
      "Florida state bills plus 31 local governments; the list below says which. A bill not appearing here does not mean it does not exist.",
    );
  });
});
