import { AlertCircle, CheckCircle2, Clock3, FileCode2, Image, Layers3, Loader2, Package, Play, UserRound } from "lucide-react"
import type { GenerationState } from "@/context/ProjectContext"
import { cn } from "@/lib/utils"

interface Props {
  generationState: GenerationState | null
  busyAction: string | null
}

type FlowStatus = "locked" | "ready" | "running" | "review" | "done" | "failed"

function statusClass(status: FlowStatus) {
  if (status === "done") return "border-emerald-200 bg-emerald-50 text-emerald-800"
  if (status === "running") return "border-blue-200 bg-blue-50 text-blue-800"
  if (status === "review") return "border-amber-200 bg-amber-50 text-amber-800"
  if (status === "failed") return "border-red-200 bg-red-50 text-red-800"
  if (status === "ready") return "border-indigo-200 bg-indigo-50 text-indigo-800"
  return "border-gray-200 bg-white text-gray-500"
}

function statusIcon(status: FlowStatus) {
  if (status === "running") return <Loader2 className="h-4 w-4 animate-spin" />
  if (status === "done") return <CheckCircle2 className="h-4 w-4" />
  if (status === "failed") return <AlertCircle className="h-4 w-4" />
  return <Clock3 className="h-4 w-4" />
}

function atOrAfter(current: GenerationState["state"] | undefined, target: GenerationState["state"]) {
  const order: GenerationState["state"][] = [
    "idle",
    "scene_outline_draft",
    "scene_outline_confirmed",
    "character_assets_draft",
    "character_assets_confirmed",
    "background_assets_draft",
    "background_assets_confirmed",
    "script_preview",
    "committed",
  ]
  return order.indexOf(current ?? "idle") >= order.indexOf(target)
}

export function GenerationFlowPanel({ generationState, busyAction }: Props) {
  const state = generationState?.state ?? "idle"
  const sceneGeneration = generationState?.scene_generation
  const sceneStatus: FlowStatus =
    sceneGeneration?.status === "failed"
      ? "failed"
      : sceneGeneration?.status === "in_progress" || busyAction === "scene-packages-all"
      ? "running"
      : sceneGeneration?.status === "complete" || atOrAfter(state, "character_assets_draft")
      ? "done"
      : "ready"
  const characterCount = Object.values(generationState?.character_assets ?? {}).filter((slot) => slot.kind === "character_sprite").length
  const backgroundCount = Object.values(generationState?.background_assets ?? {}).filter((slot) => slot.kind === "background").length

  const cards = [
    {
      label: "场景包",
      icon: <Layers3 className="h-4 w-4" />,
      status: sceneStatus,
      detail: sceneGeneration
        ? `${sceneGeneration.completed_count} / ${sceneGeneration.total_count} 个章节已完成`
        : "从冻结的蓝图派生场景包",
    },
    {
      label: "角色素材",
      icon: <UserRound className="h-4 w-4" />,
      status: atOrAfter(state, "character_assets_confirmed") ? "done" : state === "character_assets_draft" ? "review" : sceneStatus === "done" ? "ready" : "locked",
      detail: `${characterCount} 个角色槽位`,
    },
    {
      label: "场景背景",
      icon: <Image className="h-4 w-4" />,
      status: atOrAfter(state, "background_assets_confirmed") ? "done" : state === "background_assets_draft" ? "review" : atOrAfter(state, "character_assets_confirmed") ? "ready" : "locked",
      detail: `${backgroundCount} 个背景槽位`,
    },
    {
      label: "脚本预览",
      icon: <FileCode2 className="h-4 w-4" />,
      status: state === "committed" ? "done" : state === "script_preview" ? "review" : "locked",
      detail: generationState?.script_preview?.script_files?.length
        ? `已暂存 ${generationState.script_preview.script_files.length} 个脚本文件`
        : "写回前预览生成的 Ren'Py 脚本",
    },
    {
      label: "构建",
      icon: <Package className="h-4 w-4" />,
      status: state === "committed" ? "ready" : "locked",
      detail: "可在工作区顶部进行构建",
    },
    {
      label: "预览",
      icon: <Play className="h-4 w-4" />,
      status: "locked",
      detail: "Web 构建成功后解锁预览",
    },
  ] satisfies Array<{ label: string; icon: React.ReactNode; status: FlowStatus; detail: string }>

  return (
    <section data-testid="generation-flow-panel" className="rounded-lg border border-gray-200 bg-white p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-base font-semibold text-gray-900">生成流程</h3>
          <p className="mt-1 text-sm text-gray-500">跟踪从冻结蓝图到可游玩预览的生产线。</p>
        </div>
        <span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-600">{state}</span>
      </div>
      <div className="mt-4 grid gap-3 xl:grid-cols-3 2xl:grid-cols-6">
        {cards.map((card) => (
          <div key={card.label} className={cn("rounded-lg border p-3", statusClass(card.status))}>
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                {card.icon}
                <span className="text-sm font-semibold">{card.label}</span>
              </div>
              {statusIcon(card.status)}
            </div>
            <p className="mt-2 min-h-9 text-xs leading-relaxed opacity-75">{card.detail}</p>
          </div>
        ))}
      </div>
    </section>
  )
}

