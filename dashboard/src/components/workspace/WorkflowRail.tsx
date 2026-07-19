import { AlertCircle, CheckCircle2, Circle, Clock3, Lock, Loader2 } from "lucide-react"
import type { Chapter } from "@/context/ProjectContext"
import { cn } from "@/lib/utils"
import { WorkspaceSidebar } from "./WorkspaceSidebar"
import type { WorkflowStage, WorkflowStageStatus } from "./workflowState"

interface Props {
  stages: WorkflowStage[]
  chapters: Chapter[]
  selectedSceneId: string | null
  onSelectScene: (sceneId: string) => void
}

const statusIcon: Record<WorkflowStageStatus, React.ReactNode> = {
  locked: <Lock className="h-3.5 w-3.5 text-gray-400" />,
  ready: <Clock3 className="h-3.5 w-3.5 text-indigo-500" />,
  running: <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" />,
  needs_review: <AlertCircle className="h-3.5 w-3.5 text-amber-500" />,
  done: <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />,
  failed: <AlertCircle className="h-3.5 w-3.5 text-red-500" />,
}

const stageTone: Record<WorkflowStageStatus, string> = {
  locked: "text-slate-500 hover:bg-white",
  ready: "bg-indigo-50 text-indigo-800 ring-1 ring-indigo-100",
  running: "bg-blue-50 text-blue-800 ring-1 ring-blue-100",
  needs_review: "bg-amber-50 text-amber-900 ring-1 ring-amber-100",
  done: "text-slate-700 hover:bg-white",
  failed: "bg-red-50 text-red-700 ring-1 ring-red-100",
}

export function WorkflowRail({ stages, chapters, selectedSceneId, onSelectScene }: Props) {
  return (
    <aside data-testid="workflow-rail" className="flex h-full w-full flex-col bg-slate-50">
      <div className="border-b border-slate-200 p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">制作流程</h3>
          <Circle className="h-3 w-3 text-blue-500" />
        </div>
        <div className="space-y-1.5">
          {stages.map((stage) => (
            <div
              key={stage.id}
              className={cn("rounded-md px-2.5 py-2 text-xs transition-colors", stageTone[stage.status])}
            >
              <div className="flex items-center gap-2">
                {statusIcon[stage.status]}
                <span className="font-medium">{stage.label}</span>
              </div>
              <p className="mt-1 line-clamp-2 pl-5 text-[11px] opacity-70">{stage.detail}</p>
            </div>
          ))}
        </div>
      </div>
      <div className="min-h-0 flex-1">
        <WorkspaceSidebar
          chapters={chapters}
          selectedSceneId={selectedSceneId}
          onSelectScene={onSelectScene}
        />
      </div>
    </aside>
  )
}

