import { useAppStore } from '@/store/useAppStore';
import { useState } from 'react';
import { Save, RotateCcw, FileCode, ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { Scene } from '@/types';

// 模拟脚本内容
const mockScripts: Record<string, string> = {
  's1-1': `# Scene 1.1 - 初见
label scene_1_1:
    scene bg_library_morning
    play music "bgm_peaceful.mp3"

    "阳光透过图书馆的窗户洒进来，空气中弥漫着纸张和墨水的味道。"

    show sakura neutral at center
    with dissolve

    "一个女孩正站在书架前，认真地整理着书籍。"

    protagonist "那个...请问这本书可以借吗？"

    show sakura surprised at center

    sakura "啊！"

    "她被吓了一跳，手中的书差点掉在地上。"

    show sakura shy at center

    sakura "对不起，我没注意到有人...当然可以借，请跟我来。"

    "她的脸颊微微泛红，低头走向借阅台。"

    return`,

  's1-2': `# Scene 1.2 - 借书
label scene_1_2:
    scene bg_library_counter

    show sakura neutral at center

    sakura "请出示一下学生证。"

    protagonist "给你。"

    "她接过学生证，在电脑上登记。"

    sakura "《挪威的森林》...你也喜欢村上春树吗？"

    protagonist "嗯，最近刚开始看。你呢？"

    show sakura smile at center

    sakura "这是我最喜欢的书之一。每次读都会有新的感受。"

    "她的眼睛亮了起来，仿佛找到了知音。"

    return`,

  's1-3': `# Scene 1.3 - 告别
label scene_1_3:
    scene bg_library_entrance

    show sakura neutral at center

    sakura "书已经登记好了，两周内归还就可以。"

    protagonist "谢谢。对了，还不知道你的名字？"

    show sakura shy at center

    sakura "我...我叫樱。是这里的图书管理员。"

    protagonist "樱...很好听的名字。我是小林，今天刚转学过来。"

    show sakura surprised at center

    # TODO: 这里情绪需要调整 - 应该是微笑而不是惊讶
    sakura "转学生？难怪之前没见过你..."

    "她露出一个温柔的笑容。"

    sakura "欢迎来我们图书馆，以后常来哦。"

    return`,

  'default': `# 请选择场景进行编辑
#
# 使用说明:
# - label: 定义场景入口
# - scene: 切换背景
# - show: 显示角色
# - play music: 播放音乐
# - "文本": 旁白或对话`,
};

export function ScriptEditor({ onBack }: { onBack: () => void }) {
  const { selectedSceneId, chapters } = useAppStore();
  const [code, setCode] = useState(mockScripts[selectedSceneId || 'default'] || mockScripts.default);
  const [saved, setSaved] = useState(true);

  // 获取当前场景信息
  let sceneName = '';
  let chapterName = '';
  for (const ch of chapters) {
    const scene = ch.scenes.find((s: Scene) => s.id === selectedSceneId);
    if (scene) {
      sceneName = scene.name;
      chapterName = ch.name;
      break;
    }
  }

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setCode(e.target.value);
    setSaved(false);
  };

  const handleSave = () => {
    setSaved(true);
    // 模拟保存
    setTimeout(() => {
      alert('脚本已保存');
    }, 300);
  };

  const handleRegenerate = () => {
    alert('请求 AI 重新生成此场景...');
  };

  if (!selectedSceneId) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-500">
        <FileCode className="w-16 h-16 mb-4 text-gray-300" />
        <p>请从左侧选择一个场景进行编辑</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900/50">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={onBack} className="gap-1 text-gray-600 dark:text-gray-400 -ml-2">
            <ArrowLeft className="w-4 h-4" />
            返回可视化
          </Button>
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white">
              {sceneName}
            </h3>
            <p className="text-xs text-gray-500">
              {chapterName} · Scene {selectedSceneId}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {!saved && (
            <span className="text-xs text-amber-600">未保存</span>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={handleRegenerate}
            className="gap-1"
          >
            <RotateCcw className="w-4 h-4" />
            重生成
          </Button>
          <Button
            size="sm"
            onClick={handleSave}
            className="gap-1"
          >
            <Save className="w-4 h-4" />
            保存
          </Button>
        </div>
      </div>

      {/* Editor */}
      <div className="flex-1 relative">
        <textarea
          value={code}
          onChange={handleChange}
          className="w-full h-full p-4 font-mono text-sm bg-white dark:bg-gray-950 text-gray-800 dark:text-gray-200 resize-none focus:outline-none"
          spellCheck={false}
        />
      </div>

      {/* Footer */}
      <div className="px-4 py-2 border-t border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900/50 text-xs text-gray-500 flex items-center justify-between">
        <span>Ren'Py 脚本格式</span>
        <span>{code.split('\n').length} 行</span>
      </div>
    </div>
  );
}
