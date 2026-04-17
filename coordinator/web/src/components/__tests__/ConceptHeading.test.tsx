import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ChakraProvider } from "@chakra-ui/react";
import ConceptHeading from "../ConceptHeading";

const wrap = (ui: React.ReactNode) => (
  <ChakraProvider>{ui}</ChakraProvider>
);

describe("ConceptHeading", () => {
  beforeEach(() => localStorage.clear());

  it("renders heading + gloss on first mount", () => {
    render(wrap(<ConceptHeading name="place" pageKey="/places" />));
    expect(screen.getByRole("heading")).toHaveTextContent(/places/i);
    expect(screen.getByText(/bundle of hardware you reserve/i)).toBeInTheDocument();
  });

  it("collapses to info icon after the 5th mount", () => {
    localStorage.setItem("concept-visits:/places", "5");
    render(wrap(<ConceptHeading name="place" pageKey="/places" />));
    expect(screen.getByRole("heading")).toHaveTextContent(/places/i);
    expect(screen.queryByText(/bundle of hardware you reserve/i)).toBeNull();
    expect(screen.getByLabelText(/show concept/i)).toBeInTheDocument();
  });

  it("click on info icon re-expands the gloss", () => {
    localStorage.setItem("concept-visits:/places", "10");
    render(wrap(<ConceptHeading name="place" pageKey="/places" />));
    fireEvent.click(screen.getByLabelText(/show concept/i));
    expect(screen.getByText(/bundle of hardware you reserve/i)).toBeInTheDocument();
  });

  it("increments the visit counter exactly once per mount", () => {
    render(wrap(<ConceptHeading name="place" pageKey="/places" />));
    expect(localStorage.getItem("concept-visits:/places")).toBe("1");
  });
});
