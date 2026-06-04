/**
 * ArchetypeBadge.test.tsx — the bot archetype pill and its play-style tooltip.
 *
 * The solo poker trainer shows each bot's archetype on the felt. Hovering (or
 * keyboard-focusing) the badge must reveal an accessible tooltip describing how
 * that opponent plays and how to exploit them — see frontend/src/data/archetypes.ts.
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, it, expect, vi } from "vitest";
import ArchetypeBadge from "../src/components/ArchetypeBadge";
import { getArchetypeMeta } from "../src/data/archetypes";

describe("ArchetypeBadge", () => {
  it("renders the archetype name pill for a bot", () => {
    render(<ArchetypeBadge archetypeName="Maniac" isBot={true} />);
    expect(screen.getByTestId("archetype-badge-Maniac")).toBeInTheDocument();
  });

  it("does not show a tooltip until the badge is hovered or focused", () => {
    render(<ArchetypeBadge archetypeName="TAG" isBot={true} />);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("reveals an accessible play-style tooltip on hover", async () => {
    const user = userEvent.setup();
    render(<ArchetypeBadge archetypeName="Nit" isBot={true} />);
    const meta = getArchetypeMeta("Nit");
    expect(meta).not.toBeNull();

    await user.hover(screen.getByTestId("archetype-badge-Nit"));

    const tooltip = screen.getByRole("tooltip");
    expect(tooltip).toBeInTheDocument();
    // The "how they play" description and the exploit tip both surface.
    expect(within(tooltip).getByText(meta!.style)).toBeInTheDocument();
    expect(within(tooltip).getByText(meta!.exploit, { exact: false })).toBeInTheDocument();
  });

  it("shows the Tight↔Loose and Passive↔Aggressive teaching axes in the tooltip", async () => {
    const user = userEvent.setup();
    render(<ArchetypeBadge archetypeName="LAG" isBot={true} />);

    await user.hover(screen.getByTestId("archetype-badge-LAG"));

    const tooltip = screen.getByRole("tooltip");
    // Scope to the axes region so the assertions don't collide with the
    // archetype's own tagline/description (e.g. LAG → "Loose-Aggressive").
    const axes = within(tooltip).getByTestId("archetype-axes");
    expect(within(axes).getByText(/tight/i)).toBeInTheDocument();
    expect(within(axes).getByText(/loose/i)).toBeInTheDocument();
    expect(within(axes).getByText(/passive/i)).toBeInTheDocument();
    expect(within(axes).getByText(/aggressive/i)).toBeInTheDocument();
  });

  it("wires the tooltip to the trigger via aria-describedby for screen readers", async () => {
    const user = userEvent.setup();
    render(<ArchetypeBadge archetypeName="Shark" isBot={true} />);
    const trigger = screen.getByTestId("archetype-badge-Shark");

    await user.hover(trigger);

    const tooltip = screen.getByRole("tooltip");
    expect(trigger).toHaveAttribute("aria-describedby", tooltip.id);
    expect(tooltip.id).toBeTruthy();
  });

  it("opens on keyboard focus and closes on blur (no mouse required)", async () => {
    const user = userEvent.setup();
    render(<ArchetypeBadge archetypeName="CallingStation" isBot={true} />);

    // Tab moves focus to the badge (it must be focusable).
    await user.tab();
    expect(screen.getByTestId("archetype-badge-CallingStation")).toHaveFocus();
    expect(screen.getByRole("tooltip")).toBeInTheDocument();

    // Tab away → tooltip closes.
    await user.tab();
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("hides the tooltip again when the pointer leaves", async () => {
    const user = userEvent.setup();
    render(<ArchetypeBadge archetypeName="Whale" isBot={true} />);
    const trigger = screen.getByTestId("archetype-badge-Whale");

    await user.hover(trigger);
    expect(screen.getByRole("tooltip")).toBeInTheDocument();

    await user.unhover(trigger);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("does not attach a play-style tooltip to the human 'You' badge", async () => {
    const user = userEvent.setup();
    render(<ArchetypeBadge archetypeName={null} isBot={false} />);
    const badge = screen.getByTestId("archetype-badge-human");

    await user.hover(badge);

    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("renders an unknown archetype without crashing and shows no tooltip", async () => {
    const user = userEvent.setup();
    render(<ArchetypeBadge archetypeName="Wizard" isBot={true} />);
    const badge = screen.getByTestId("archetype-badge-Wizard");
    expect(badge).toBeInTheDocument();

    await user.hover(badge);

    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });
});

describe("ArchetypeBadge viewport-aware placement", () => {
  let rectSpy: { mockRestore: () => void } | undefined;

  function setViewport(height: number, width = 1024) {
    Object.defineProperty(window, "innerHeight", { value: height, configurable: true });
    Object.defineProperty(window, "innerWidth", { value: width, configurable: true });
  }

  function mockTriggerRect(rect: Partial<DOMRect>) {
    rectSpy = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      top: 0,
      bottom: 0,
      left: 0,
      right: 0,
      width: 0,
      height: 0,
      x: 0,
      y: 0,
      toJSON: () => ({}),
      ...rect,
    } as DOMRect);
  }

  afterEach(() => {
    rectSpy?.mockRestore();
    rectSpy = undefined;
    setViewport(768);
  });

  it("anchors the tooltip ABOVE when the badge sits near the viewport bottom", async () => {
    const user = userEvent.setup();
    setViewport(400);
    mockTriggerRect({ top: 360, bottom: 384, left: 120, right: 160, width: 40, height: 24 });
    render(<ArchetypeBadge archetypeName="TAG" isBot={true} />);

    await user.hover(screen.getByTestId("archetype-badge-TAG"));

    const tooltip = screen.getByRole("tooltip");
    // Anchored from its bottom edge so it grows upward into the room above.
    expect(tooltip.style.transform).toBe("translate(-50%, -100%)");
    // Height budget is capped to the available space and never exceeds the viewport.
    const maxH = parseFloat(tooltip.style.maxHeight);
    expect(maxH).toBeGreaterThan(0);
    expect(maxH).toBeLessThanOrEqual(400);
  });

  it("flips the tooltip BELOW when the badge sits near the top of a short viewport", async () => {
    const user = userEvent.setup();
    setViewport(400);
    mockTriggerRect({ top: 12, bottom: 36, left: 120, right: 160, width: 40, height: 24 });
    render(<ArchetypeBadge archetypeName="LAG" isBot={true} />);

    await user.hover(screen.getByTestId("archetype-badge-LAG"));

    const tooltip = screen.getByRole("tooltip");
    expect(tooltip.style.transform).toBe("translateX(-50%)");
    const maxH = parseFloat(tooltip.style.maxHeight);
    expect(maxH).toBeGreaterThan(0);
    expect(maxH).toBeLessThanOrEqual(400);
  });
});
