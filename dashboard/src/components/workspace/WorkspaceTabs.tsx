import { FileText, Map, Code, ArrowLeft, BookOpen, ListOrdered, MessageSquarePlus } from "lucide-react";
import { cn } from "@/lib/utils";

export type WorkspaceTab =
  | "intake"
  | "brief"
  | "outline"
  | "blueprint"
  | "storymap"
  | "generation"
  | "scene";

interface Props {
  activeTab: WorkspaceTab;
  onChange: (tab: WorkspaceTab) => void;
  hasSceneSelected: boolean;
  onBackToOverview?: () => void;
}

export function WorkspaceTabs({ activeTab, onChange, hasSceneSelected, onBackToOverview }: Props) {
  if (hasSceneSelected && activeTab === "scene") {
    return (
      <div className="border-b border-gray-200 flex items-center justify-between bg-white">
        <div className="flex">
          <TabButton
            active={activeTab === "scene"}
            onClick={() => onChange("scene")}
            icon={<Code className="w-4 h-4" />}
            label="Scene"
          />
        </div>
        {onBackToOverview && (
          <button
            onClick={onBackToOverview}
            className="flex items-center gap-1.5 mr-4 text-xs font-medium text-gray-600 hover:text-gray-900 px-2 py-1 rounded hover:bg-gray-100 transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Back to overview
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="border-b border-gray-200 flex items-center bg-white">
      <div className="flex">
        <TabButton
          active={activeTab === "intake"}
          onClick={() => onChange("intake")}
          icon={<MessageSquarePlus className="w-4 h-4" />}
          label="Intake"
        />
        <TabButton
          active={activeTab === "brief"}
          onClick={() => onChange("brief")}
          icon={<BookOpen className="w-4 h-4" />}
          label="Brief"
        />
        <TabButton
          active={activeTab === "outline"}
          onClick={() => onChange("outline")}
          icon={<ListOrdered className="w-4 h-4" />}
          label="Outline"
        />
        <TabButton
          active={activeTab === "blueprint"}
          onClick={() => onChange("blueprint")}
          icon={<FileText className="w-4 h-4" />}
          label="Blueprint"
        />
        <TabButton
          active={activeTab === "generation"}
          onClick={() => onChange("generation")}
          icon={<Code className="w-4 h-4" />}
          label="Generation"
        />
        <TabButton
          active={activeTab === "storymap"}
          onClick={() => onChange("storymap")}
          icon={<Map className="w-4 h-4" />}
          label="Story Map"
        />
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors",
        active
          ? "border-blue-500 text-blue-700"
          : "border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50"
      )}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}
