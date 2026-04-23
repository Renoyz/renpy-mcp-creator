import { Sparkles, FileText, Wand2, Lightbulb, Loader2, ArrowLeft, Construction } from "lucide-react";
import { useState } from "react";
import type { BlueprintPhase, GenerationProgress } from "@/context/ProjectContext";
import { BlueprintDraftCard } from "./BlueprintDraftCard";

interface Props {
  phase: BlueprintPhase;
  generationProgress: GenerationProgress | null;
  onStartAI: () => void;
}

export function WorkspaceOnboardingView({
  phase,
  generationProgress,
  onStartAI,
}: Props) {
  const [showManualPlaceholder, setShowManualPlaceholder] = useState(false);

  if (showManualPlaceholder) {
    return (
      <div className="h-full overflow-y-auto p-8 flex items-center justify-center">
        <div className="max-w-xl w-full bg-white rounded-xl border border-gray-200 shadow-sm p-8 text-center">
          <div className="w-16 h-16 rounded-2xl bg-amber-100 flex items-center justify-center mx-auto mb-6">
            <Construction className="w-8 h-8 text-amber-600" />
          </div>
          <h2 className="text-2xl font-bold text-gray-900 mb-2">
            手动 YAML 编辑功能即将推出
          </h2>
          <p className="text-sm text-gray-500 mb-6">
            你稍后可以直接在这里编写或粘贴 YAML 蓝图文件。目前请先使用 AI 生成蓝图。
          </p>
          <button
            onClick={() => setShowManualPlaceholder(false)}
            className="inline-flex items-center gap-2 rounded-md border border-gray-300 bg-white px-5 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            返回
          </button>
        </div>
      </div>
    );
  }

  if (phase === "generating") {
    return (
      <div className="h-full flex items-center justify-center p-8">
        <div className="max-w-md w-full text-center">
          <div className="w-16 h-16 rounded-2xl bg-blue-100 flex items-center justify-center mx-auto mb-6">
            <Loader2 className="w-8 h-8 text-blue-600 animate-spin" />
          </div>
          <h2 className="text-xl font-bold text-gray-900 mb-2">正在生成蓝图</h2>
          <p className="text-sm text-gray-500 mb-4">
            {generationProgress?.step || "正在处理..."}
          </p>
          <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 transition-all duration-500"
              style={{ width: `${generationProgress?.percent ?? 0}%` }}
            />
          </div>
          <p className="text-xs text-gray-400 mt-2">
            {generationProgress?.percent ?? 0}%
          </p>
        </div>
      </div>
    );
  }

  if (phase === "reviewing") {
    return (
      <div className="h-full overflow-y-auto p-6">
        <div className="max-w-2xl mx-auto space-y-6">
          <div className="text-center">
            <h2 className="text-xl font-bold text-gray-900">蓝图草案已生成</h2>
            <p className="text-sm text-gray-500 mt-1">
              请查看下方的草案内容，确认后我们将开始正式生成。
            </p>
          </div>
          <BlueprintDraftCard />
        </div>
      </div>
    );
  }

  const isActive = phase === "collecting";

  return (
    <div className="h-full overflow-y-auto p-8 flex items-center justify-center">
      <div className="max-w-xl w-full bg-white rounded-xl border border-gray-200 shadow-sm">
        <div className="p-8 text-center">
          {isActive ? (
            <>
              <div className="w-16 h-16 rounded-2xl bg-blue-100 flex items-center justify-center mx-auto mb-6">
                <Loader2 className="w-8 h-8 text-blue-600 animate-spin" />
              </div>

              <h2 className="text-2xl font-bold text-gray-900 mb-2">
                正在与 AI 细化需求...
              </h2>
              <p className="text-sm text-gray-500 mb-6">
                你可以在 AI 面板中继续补充想法。AI 会根据你的描述生成蓝图。
              </p>

              <div className="text-left bg-gray-50 rounded-xl p-4">
                <p className="text-sm text-gray-600">
                  💡 小贴士：尽量描述你想要的章节数、主角人设、故事基调以及是否需要分支结局，这样生成的蓝图会更符合预期。
                </p>
              </div>
            </>
          ) : (
            <>
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500 to-purple-500 flex items-center justify-center mx-auto mb-6">
                <Sparkles className="w-8 h-8 text-white" />
              </div>

              <h2 className="text-2xl font-bold text-gray-900 mb-2">
                项目已创建，开始构建蓝图吧
              </h2>
              <p className="text-sm text-gray-500 mb-8">
                蓝图是整个视觉小说的骨架。你可以让 AI 自动生成，也可以直接编写 YAML 文件。
              </p>

              <div className="flex flex-col sm:flex-row gap-3 justify-center mb-8">
                <button
                  onClick={onStartAI}
                  className="inline-flex items-center justify-center gap-2 rounded-md bg-gray-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-gray-800 transition-colors flex-1"
                >
                  <Wand2 className="w-4 h-4" />
                  让 AI 生成蓝图
                </button>
                <button
                  onClick={() => setShowManualPlaceholder(true)}
                  className="inline-flex items-center justify-center gap-2 rounded-md border border-gray-300 bg-white px-5 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors flex-1"
                >
                  <FileText className="w-4 h-4" />
                  手动准备 YAML（即将支持）
                </button>
              </div>

              <div className="text-left bg-gray-50 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Lightbulb className="w-4 h-4 text-yellow-500" />
                  <span className="text-sm font-medium text-gray-700">
                    试试这些快捷指令
                  </span>
                </div>
                <div className="flex flex-wrap gap-2">
                  <ExamplePill text="生成一个 3 章的校园恋爱故事" />
                  <ExamplePill text="设计带有分支结局的悬疑剧本" />
                  <ExamplePill text="基于《挪威的森林》的风格写蓝图" />
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function ExamplePill({ text }: { text: string }) {
  return (
    <span className="inline-block px-3 py-1.5 text-xs rounded-full bg-white border border-gray-200 text-gray-600">
      {text}
    </span>
  );
}
