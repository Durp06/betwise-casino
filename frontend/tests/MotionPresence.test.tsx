/**
 * MotionPresence.test.tsx — the site-wide presence primitives (P7).
 *
 * These wrap content with framer-motion enter/exit; the behavior worth asserting
 * is that they render their children (no content is hidden by the animation) and
 * that ModalShell's backdrop closes while the panel does not.
 */
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import ModalShell from "../src/motion/presence/ModalShell";
import FadeSlide from "../src/motion/presence/FadeSlide";
import RouteFade from "../src/motion/presence/RouteFade";
import { StaggerList, StaggerItem } from "../src/motion/presence/StaggerList";

describe("ModalShell", () => {
  it("renders its children inside a labelled dialog", () => {
    render(
      <ModalShell onClose={() => {}} ariaLabel="Test dialog" panelClassName="panel">
        <button>Inside</button>
      </ModalShell>,
    );
    expect(screen.getByRole("dialog", { name: "Test dialog" })).toBeInTheDocument();
    expect(screen.getByText("Inside")).toBeInTheDocument();
  });

  it("closes on backdrop click but not on panel click", () => {
    const onClose = vi.fn();
    render(
      <ModalShell onClose={onClose} ariaLabel="Test dialog" panelClassName="panel">
        <button>Inside</button>
      </ModalShell>,
    );

    // Clicking content inside the panel must NOT close (stopPropagation).
    fireEvent.click(screen.getByText("Inside"));
    expect(onClose).not.toHaveBeenCalled();

    // Clicking the backdrop itself closes.
    fireEvent.click(screen.getByRole("dialog"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("StaggerList / StaggerItem", () => {
  it("renders every item", () => {
    render(
      <StaggerList className="flex flex-col">
        <StaggerItem>Alpha</StaggerItem>
        <StaggerItem>Bravo</StaggerItem>
        <StaggerItem>Charlie</StaggerItem>
      </StaggerList>,
    );
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Bravo")).toBeInTheDocument();
    expect(screen.getByText("Charlie")).toBeInTheDocument();
  });
});

describe("FadeSlide", () => {
  it("renders its children", () => {
    render(<FadeSlide className="x">Banner text</FadeSlide>);
    expect(screen.getByText("Banner text")).toBeInTheDocument();
  });
});

describe("RouteFade", () => {
  it("renders the page content for a pathname", () => {
    render(
      <RouteFade pathname="/lobby">
        <div>Page content</div>
      </RouteFade>,
    );
    expect(screen.getByText("Page content")).toBeInTheDocument();
  });
});
