import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StoryMapWorkspaceView } from "./StoryMapWorkspaceView";

describe("StoryMapWorkspaceView", () => {
  it("opens the selected scene when a scene node is clicked", async () => {
    const user = userEvent.setup();
    const onSelectScene = vi.fn();

    render(
      <StoryMapWorkspaceView
        storymap={{
          nodes: [
            { id: "s1", chapter_id: "ch1", scene_id: "s1", type: "normal", label: "First Scene" },
          ],
          edges: [],
        }}
        chapters={[
          {
            id: "ch1",
            name: "Chapter One",
            order: 1,
            scenes: [{ id: "s1", name: "First Scene", order: 1, status: "pending" }],
          },
        ]}
        onSelectScene={onSelectScene}
      />
    );

    await user.click(screen.getByRole("button", { name: /first scene/i }));

    expect(onSelectScene).toHaveBeenCalledWith("s1");
  });
});
