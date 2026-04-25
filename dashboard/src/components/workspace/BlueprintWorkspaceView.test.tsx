import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { BlueprintWorkspaceView } from "./BlueprintWorkspaceView";

describe("BlueprintWorkspaceView", () => {
  it("prefers live chapter scene counts over empty blueprint chapter scenes", () => {
    render(
      <BlueprintWorkspaceView
        blueprint={{
          title: "Test Project",
          genre: "Wuxia",
          worldview: "Ancient jianghu",
          chapters: [
            {
              id: "ch1",
              name: "Chapter One",
              order: 1,
              scenes: [],
            },
          ],
        }}
        chapters={[
          {
            id: "ch1",
            name: "Chapter One",
            order: 1,
            scenes: [
              { id: "s1", name: "First Scene", order: 1, status: "pending" },
              { id: "s2", name: "Second Scene", order: 2, status: "confirmed" },
            ],
          },
        ]}
        refinementStatus={null}
        onFreeze={vi.fn()}
      />
    );

    expect(screen.getByText(/1 章节/i)).toBeInTheDocument();
    expect(screen.getByText(/2 场景/i)).toBeInTheDocument();
    expect(screen.getByText(/已确认 1 个/i)).toBeInTheDocument();
    expect(screen.getByText("First Scene")).toBeInTheDocument();
    expect(screen.getByText("Second Scene")).toBeInTheDocument();
  });
});
