// AI contribution: 50% or more AI-generated
/** Sidebar view store (#408): default screen, switching, and the screen list. */
import { afterEach, describe, expect, it } from "vitest";
import { VIEWS, useViewStore } from "../../src/store/useViewStore";

afterEach(() => useViewStore.setState({ activeView: "station" }));

describe("useViewStore", () => {
  it("starts on the station view", () => {
    expect(useViewStore.getState().activeView).toBe("station");
  });

  it("switches to the requested view and back", () => {
    useViewStore.getState().setView("compare");
    expect(useViewStore.getState().activeView).toBe("compare");

    useViewStore.getState().setView("station");
    expect(useViewStore.getState().activeView).toBe("station");
  });

  it("lists the five Release 2 screens once each, in sidebar order", () => {
    expect(VIEWS.map((view) => view.label)).toStrictEqual(
      ["Station view", "Compare", "Results", "Scenario setup", "Sources"]);
    expect(new Set(VIEWS.map((view) => view.id)).size).toBe(VIEWS.length);
  });
});
