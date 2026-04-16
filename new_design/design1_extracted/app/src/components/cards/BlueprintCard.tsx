import { useAppStore } from '@/store/useAppStore';
import { useChatStore } from '@/store/useChatStore';
import { Users, BookOpen, CheckCircle2, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface BlueprintCardProps {
  data: {
    title: string;
    genre: string;
    characters: { name: string; role: string }[];
    chapters: { name: string; scenes: number }[];
  };
}

export function BlueprintCard({ data }: BlueprintCardProps) {
  const { confirmBlueprint } = useAppStore();
  const { addAssistantMessage } = useChatStore();

  const handleConfirm = () => {
    confirmBlueprint();
    addAssistantMessage(
      'Blueprint 已确认！开始生成第一章...',
      'progress',
      {
        chapterId: 'ch1',
        sceneId: 's1-1',
        sceneName: '初见',
        step: '准备生成...',
        percent: 10,
      }
    );
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 bg-gradient-to-r from-purple-500 to-pink-500">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-white" />
          <span className="font-semibold text-white">项目蓝图</span>
        </div>
      </div>

      {/* Content */}
      <div className="p-4 space-y-4">
        {/* Title & Genre */}
        <div>
          <h4 className="font-bold text-gray-900 dark:text-white">{data.title}</h4>
          <p className="text-sm text-gray-500">{data.genre}</p>
        </div>

        {/* Characters */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Users className="w-4 h-4 text-purple-500" />
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
              角色 ({data.characters.length})
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            {data.characters.map((char, index) => (
              <span
                key={index}
                className="px-2 py-1 rounded-full bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 text-xs"
              >
                {char.name}
              </span>
            ))}
          </div>
        </div>

        {/* Chapters */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <BookOpen className="w-4 h-4 text-blue-500" />
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
              章节 ({data.chapters.length})
            </span>
          </div>
          <div className="space-y-1">
            {data.chapters.map((chapter, index) => (
              <div
                key={index}
                className="flex items-center justify-between text-sm"
              >
                <span className="text-gray-600 dark:text-gray-400">{chapter.name}</span>
                <span className="text-gray-400">{chapter.scenes} 场景</span>
              </div>
            ))}
          </div>
        </div>

        {/* Actions */}
        <Button
          onClick={handleConfirm}
          className="w-full gap-2"
        >
          <CheckCircle2 className="w-4 h-4" />
          确认并生成
        </Button>
      </div>
    </div>
  );
}
