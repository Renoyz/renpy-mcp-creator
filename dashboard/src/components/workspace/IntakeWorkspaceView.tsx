import type { RefinementIntake } from "@/context/ProjectContext";
import { AlertCircle, Bot, CheckCircle2, ClipboardList, MessageCircle, MessageSquarePlus } from "lucide-react";

interface Props {
  intake: RefinementIntake | null;
  error?: string | null;
  projectName: string;
  onPromoteBriefDraft: (projectName: string) => Promise<void>;
  onPromoteOutlineDraft: (projectName: string) => Promise<void>;
  onStartAI?: () => void;
}

const SLOT_LABELS: Record<string, string> = {
  core_premise: "核心设定",
  audience_genre: "受众 / 类型",
  tone_themes: "基调 / 主题",
  visual_style: "视觉风格",
  world_rules: "世界规则",
  core_cast: "核心角色",
  character_identity: "角色身份",
  relationship_baselines: "关系基线",
  constraints: "约束条件",
};

function formatSlotLabel(key: string): string {
  return (
    SLOT_LABELS[key] ??
    key
      .split("_")
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ")
  );
}

const PROJECT_SLOT_KEYS = [
  "core_premise",
  "audience_genre",
  "tone_themes",
  "visual_style",
  "world_rules",
  "core_cast",
  "character_identity",
  "relationship_baselines",
  "constraints",
];

function formatSlotValue(value: unknown): string {
  if (value == null || value === "") return "尚未收集到内容。";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

export function IntakeWorkspaceView({
  intake,
  error,
  projectName,
  onPromoteBriefDraft,
  onPromoteOutlineDraft,
  onStartAI,
}: Props) {
  if (error) {
    return (
      <div className="h-full overflow-auto p-6">
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
          <div className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0" />
            <div>
              <h2 className="text-sm font-semibold">加载需求采集数据失败</h2>
              <p className="mt-1 text-sm opacity-90">{error}</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!intake) {
    return (
      <div className="h-full overflow-auto p-6">
        <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-6">
          <div className="flex items-start gap-3">
            <Bot className="mt-0.5 h-5 w-5 flex-shrink-0 text-blue-600" />
            <div className="flex-1">
              <h2 className="text-base font-semibold text-gray-900">开始项目需求采集</h2>
              <p className="mt-1 text-sm text-gray-600">
                先让 AI 助手询问几个项目级问题。这一步会生成第一份项目简报草稿，之后你再进入结构化审阅。
              </p>
              <button
                type="button"
                onClick={onStartAI}
                className="mt-4 inline-flex items-center gap-2 rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
              >
                <MessageSquarePlus className="h-4 w-4" />
                开始 AI 需求采集
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const isChapterPhase = intake.phase === "chapter" || intake.phase === "outline_ready";
  const slotKeys = Array.from(new Set([...PROJECT_SLOT_KEYS, ...Object.keys(intake.slots)]));
  const completedSlots = slotKeys.filter((key) => intake.slots[key]?.complete).length;
  const totalSlots = slotKeys.length;
  const remainingSlots = Math.max(0, totalSlots - completedSlots);
  const progressPercent = totalSlots > 0 ? Math.round((completedSlots / totalSlots) * 100) : 0;
  const nextStep = !isChapterPhase && intake.brief_draft_ready
    ? "下一步：进入简报审阅"
    : isChapterPhase && intake.outline_draft_ready
    ? "下一步：进入大纲审阅"
    : "下一步：继续与 AI 对话";

  return (
    <div className="h-full overflow-auto bg-slate-50 p-6">
      <div className="max-w-7xl space-y-6">
        <div
          data-testid="intake-progress-panel"
          className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm"
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-blue-700">
                <ClipboardList className="h-4 w-4" />
                <span>需求采集 / {intake.phase}</span>
              </div>
              <h2 className="mt-2 text-xl font-semibold tracking-tight text-slate-950">
                {isChapterPhase ? "章节采集进度" : "项目采集进度"}
              </h2>
              <p className="mt-1 text-sm text-slate-600">{nextStep}</p>
            </div>
            {!isChapterPhase && intake.brief_draft_ready && (
              <button
                type="button"
                onClick={() => void onPromoteBriefDraft(projectName)}
                data-testid="promote-brief-draft"
                className="inline-flex items-center gap-2 rounded-md bg-slate-950 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800"
              >
                <CheckCircle2 className="h-4 w-4" />
                进入简报审阅
              </button>
            )}
            {isChapterPhase && intake.outline_draft_ready && (
              <button
                type="button"
                onClick={() => void onPromoteOutlineDraft(projectName)}
                data-testid="promote-outline-draft"
                className="inline-flex items-center gap-2 rounded-md bg-slate-950 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800"
              >
                <CheckCircle2 className="h-4 w-4" />
                进入大纲审阅
              </button>
            )}
          </div>

          {!isChapterPhase && (
            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3">
                <div className="text-xs font-medium text-slate-500">已收集</div>
                <div className="mt-1 text-lg font-semibold text-slate-950">
                  {completedSlots} / {totalSlots} 项已收集
                </div>
              </div>
              <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3">
                <div className="text-xs font-medium text-amber-700">待完成</div>
                <div className="mt-1 text-lg font-semibold text-amber-950">剩余 {remainingSlots} 项</div>
              </div>
              <div className="rounded-md border border-blue-200 bg-blue-50 px-4 py-3">
                <div className="text-xs font-medium text-blue-700">下一步行动</div>
                <div className="mt-1 flex items-center gap-2 text-sm font-semibold text-blue-950">
                  <MessageCircle className="h-4 w-4" />
                  {intake.brief_draft_ready ? "审阅简报" : "回答 AI 提问"}
                </div>
              </div>
            </div>
          )}

          {!isChapterPhase && (
            <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-blue-600 transition-all"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          )}

          <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">当前理解</div>
            <p className="mt-2 text-sm leading-6 text-slate-700">
              {intake.current_summary || "AI 助手已开始采集，但尚未整理出可用的摘要。"}
            </p>
          </div>
          {isChapterPhase && !intake.outline_draft_ready && (
            <div className="mt-4 rounded-md border border-blue-200 bg-blue-50 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-blue-900">正在准备大纲审阅</div>
                  <p className="mt-1 text-xs text-blue-700">
                    章节采集仍在进行中。请继续与 AI 助手协作，直到大纲草稿就绪。
                  </p>
                </div>
              </div>
              <div
                data-testid="outline-phase-progress"
                className="mt-3 h-2 w-full overflow-hidden rounded-full bg-blue-100"
              >
                <div className="h-full w-1/2 animate-pulse rounded-full bg-blue-600" />
              </div>
            </div>
          )}
        </div>

        {isChapterPhase && intake.chapter_draft.length > 0 && (
          <div className="rounded-lg border border-gray-200 bg-white p-5">
            <h3 className="text-sm font-semibold text-gray-900">章节草稿</h3>
            <div className="mt-4 space-y-3">
              {intake.chapter_draft.map((ch) => (
                <div key={ch.chapter_id} className="rounded-md border border-gray-200 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-sm font-medium text-gray-900">
                      {ch.chapter_name || ch.chapter_id}
                    </div>
                    <span className="text-xs text-gray-500">顺序 {ch.order}</span>
                  </div>
                  {ch.chapter_goal && (
                    <p className="mt-1 text-xs text-gray-600"><span className="font-medium">目标：</span> {ch.chapter_goal}</p>
                  )}
                  {ch.key_conflict && (
                    <p className="mt-1 text-xs text-gray-600"><span className="font-medium">冲突：</span> {ch.key_conflict}</p>
                  )}
                  {ch.emotional_arc && (
                    <p className="mt-1 text-xs text-gray-600"><span className="font-medium">弧线：</span> {ch.emotional_arc}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {!isChapterPhase && (
          <section data-testid="intake-requirements-grid" className="space-y-4">
            <div className="flex items-end justify-between gap-4">
              <div>
                <h3 className="text-base font-semibold text-slate-950">需求清单</h3>
                <p className="mt-1 text-sm text-slate-600">
                  查看 AI 在结构化审阅前已收集的简报要素。
                </p>
              </div>
              <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-600 shadow-sm ring-1 ring-slate-200">
                {remainingSlots === 0 ? "可以进入审阅" : `还差 ${remainingSlots} 项`}
              </span>
            </div>

            <div className="grid gap-3 2xl:grid-cols-4 xl:grid-cols-3 md:grid-cols-2">
              {slotKeys.map((key) => {
                const slot = intake.slots[key];
                const complete = !!slot?.complete;
                return (
                  <div
                    key={key}
                    className={`rounded-lg border bg-white p-4 shadow-sm ${
                      complete ? "border-emerald-200" : "border-slate-200"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-sm font-semibold text-slate-950">{formatSlotLabel(key)}</div>
                      <span
                        className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                          complete ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"
                        }`}
                      >
                        {complete ? "已完成" : "缺失"}
                      </span>
                    </div>
                    <div className="mt-3 line-clamp-4 break-words text-sm leading-6 text-slate-600">
                      {formatSlotValue(slot?.value)}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
