import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ChakraProvider } from "@chakra-ui/react";
import Term from "../Term";

const wrap = (ui: React.ReactNode) => (
  <ChakraProvider>{ui}</ChakraProvider>
);

describe("Term", () => {
  beforeEach(() => localStorage.clear());

  it("underlines on first render", () => {
    render(wrap(<Term name="match">match</Term>));
    const el = screen.getByText("match");
    expect(el).toHaveStyle("text-decoration-style: dotted");
  });

  it("suppresses underline after the localStorage flag is set", () => {
    localStorage.setItem("concept-term-seen:match", "1");
    render(wrap(<Term name="match">match</Term>));
    const el = screen.getByText("match");
    expect(el).not.toHaveStyle("text-decoration-style: dotted");
  });

  it("sets the seen flag on first mouse-enter", () => {
    render(wrap(<Term name="match">match</Term>));
    const el = screen.getByText("match");
    fireEvent.mouseEnter(el);
    expect(localStorage.getItem("concept-term-seen:match")).toBe("1");
  });

  it("sets the seen flag on first keyboard focus", () => {
    render(wrap(<Term name="match">match</Term>));
    const el = screen.getByText("match");
    fireEvent.focus(el);
    expect(localStorage.getItem("concept-term-seen:match")).toBe("1");
  });
});
