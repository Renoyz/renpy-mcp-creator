import { CheckCircle, RefreshCw, Users, Clock, Palette, Music, Sparkles } from "lucide-react";
import { useProject } from "@/context/ProjectContext";

export function BlueprintDraftCard() {
  const { blueprintDraft, sendBlueprintConfirmation } = useProject();
  const draft = blueprintDraft;

  if (!draft) {
    return (
      <div className="text-center text-gray-400 py-12">
        暂无蓝图草案数据
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 bg-gradient-to-r from-purple-500 to-pink-500">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-white" />
          <span className="font-semibold text-white">项目蓝图</span>
        </div>
      </div>
      <div className="p-6 space-y-6">
        {/* Title & Genre */}
        <div>
          <h3 className="text-lg font-bold text-gray-900">{draft.title || "未命名项目"}</h3>
          <div className="flex flex-wrap items-center gap-3 mt-2">
            {draft.genre && (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 text-xs font-medium rounded-full bg-purple-100 text-purple-700">
                {draft.genre}
              </span>
            )}
            {draft.target_audience && (
              <span className="inline-flex items-center gap-1 text-xs text-gray-500">
                <Users className="w-3 h-3" />
                {draft.target_audience}
              </span>
            )}
            {draft.estimated_play_time && (
              <span className="inline-flex items-center gap-1 text-xs text-gray-500">
                <Clock className="w-3 h-3" />
                {draft.estimated_play_time}
              </span>
            )}
            {draft.art_style && (
              <span className="inline-flex items-center gap-1 text-xs text-gray-500">
                <Palette className="w-3 h-3" />
                {draft.art_style}
              </span>
            )}
            {draft.audio_style && (
              <span className="inline-flex items-center gap-1 text-xs text-gray-500">
                <Music className="w-3 h-3" />
                {draft.audio_style}
              </span>
            )}
          </div>
        </div>

        {/* Worldview */}
        {draft.worldview && (
          <div>
            <h4 className="text-sm font-semibold text-gray-700 mb-1">世界观</h4>
            <p className="text-sm text-gray-600">{draft.worldview}</p>
          </div>
        )}

        {/* Themes */}
        {draft.themes && draft.themes.length > 0 && (
          <div>
            <h4 className="text-sm font-semibold text-gray-700 mb-2">核心主题</h4>
            <div className="flex flex-wrap gap-2">
              {draft.themes.map((theme) => (
                <span
                  key={theme}
                  className="inline-block px-2.5 py-1 text-xs rounded-md bg-blue-50 text-blue-700"
                >
                  {theme}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Characters */}
        {draft.characters && draft.characters.length > 0 && (
          <div>
            <h4 className="text-sm font-semibold text-gray-700 mb-2">
              角色设定（{draft.characters.length}位）
            </h4>
            <div className="space-y-2">
              {draft.characters.map((char, idx) => (
                <div
                  key={idx}
                  className="flex items-start gap-3 p-3 rounded-lg bg-gray-50"
                >
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-400 to-purple-400 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
                    {char.name?.charAt(0) || "?"}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-gray-900">
                        {char.name || `角色${idx + 1}`}
                      </span>
                      <span className="text-xs text-gray-500">{char.role}</span>
                    </div>
                    <p className="text-xs text-gray-600 mt-0.5">{char.personality}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Chapters Preview */}
        {draft.chapters && draft.chapters.length > 0 && (
          <div>
            <h4 className="text-sm font-semibold text-gray-700 mb-2">
              章节大纲（{draft.chapters.length}章）
            </h4>
            <div className="space-y-2">
              {draft.chapters.map((ch) => (
                <div
                  key={ch.id}
                  className="flex items-center gap-3 p-3 rounded-lg bg-gray-50"
                >
                  <div className="w-6 h-6 rounded bg-blue-100 flex items-center justify-center text-xs font-bold text-blue-600 flex-shrink-0">
                    {ch.order}
                  </div>
                  <div className="flex-1 min-w-0">
                    <span className="text-sm font-medium text-gray-900">{ch.name}</span>
                    <span className="text-xs text-gray-500 ml-2">
                      {ch.scenes?.length || 0} 场景
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="px-6 py-4 border-t border-gray-200 flex items-center justify-between">
        <button
          onClick={() => sendBlueprintConfirmation(false)}
          className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          继续调整
        </button>
        <button
          onClick={() => sendBlueprintConfirmation(true)}
          className="inline-flex items-center gap-1.5 rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 transition-colors"
        >
          <CheckCircle className="w-4 h-4" />
          确认并生成
        </button>
      </div>
    </div>
  );
}
