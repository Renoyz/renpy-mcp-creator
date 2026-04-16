import { useAppStore } from '@/store/useAppStore';
import { Play, RefreshCw, Image, Music, Wand2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { Scene } from '@/types';

export function QuickActions() {
  const { selectedChapterId, selectedSceneId, chapters } = useAppStore();

  // 获取当前选中的章节/场景信息
  let currentChapter = null;

  for (const ch of chapters) {
    if (selectedChapterId === ch.id) {
      currentChapter = ch;
    }
    const scene = ch.scenes.find((s: Scene) => s.id === selectedSceneId);
    if (scene) {
      currentChapter = ch;
      break;
    }
  }

  const handlePlay = () => {
    if (currentChapter) {
      alert(`试玩: ${currentChapter.name}`);
    } else {
      alert('请先选择一个章节');
    }
  };

  const handleRegenerateBg = () => {
    alert('重新生成背景...');
  };

  const handleRegenerateChar = () => {
    alert('重新生成角色...');
  };

  return (
    <div className="w-full h-full bg-gray-50/50 dark:bg-gray-900/50 border-l border-gray-200 dark:border-gray-800 p-4">
      <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-4">
        快捷操作
      </h3>

      <div className="space-y-2">
        {/* Play Button */}
        <Button
          onClick={handlePlay}
          className="w-full gap-2 justify-start"
          variant="default"
        >
          <Play className="w-4 h-4" />
          试玩本章
        </Button>

        {/* Regenerate Actions */}
        <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
          <p className="text-xs text-gray-500 mb-3">重新生成</p>

          <div className="space-y-2">
            <Button
              onClick={handleRegenerateBg}
              variant="outline"
              className="w-full gap-2 justify-start"
              size="sm"
            >
              <Image className="w-4 h-4" />
              背景
            </Button>

            <Button
              onClick={handleRegenerateChar}
              variant="outline"
              className="w-full gap-2 justify-start"
              size="sm"
            >
              <RefreshCw className="w-4 h-4" />
              角色
            </Button>

            <Button
              variant="outline"
              className="w-full gap-2 justify-start"
              size="sm"
            >
              <Music className="w-4 h-4" />
              音乐
            </Button>

            <Button
              variant="outline"
              className="w-full gap-2 justify-start"
              size="sm"
            >
              <Wand2 className="w-4 h-4" />
              全部
            </Button>
          </div>
        </div>

        {/* Resources Preview */}
        <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
          <p className="text-xs text-gray-500 mb-3">资源预览</p>

          <div className="grid grid-cols-2 gap-2">
            <div className="aspect-square rounded-lg bg-gray-200 dark:bg-gray-800 flex items-center justify-center">
              <Image className="w-6 h-6 text-gray-400" />
            </div>
            <div className="aspect-square rounded-lg bg-gray-200 dark:bg-gray-800 flex items-center justify-center">
              <Image className="w-6 h-6 text-gray-400" />
            </div>
            <div className="aspect-square rounded-lg bg-gray-200 dark:bg-gray-800 flex items-center justify-center">
              <Image className="w-6 h-6 text-gray-400" />
            </div>
            <div className="aspect-square rounded-lg bg-gray-200 dark:bg-gray-800 flex items-center justify-center">
              <span className="text-xs text-gray-400">+3</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
