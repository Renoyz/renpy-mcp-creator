import { useAppStore } from '@/store/useAppStore';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Code,
  RefreshCw,
  CheckCircle2,
  Play,
  Image,
  Music,
  User,
  GitFork,
  ArrowRight,
} from 'lucide-react';
import type { Scene } from '@/types';
import { cn } from '@/lib/utils';
import { useState, useMemo } from 'react';

// 模拟脚本内容
const mockScripts: Record<string, string> = {
  's1-1': `# Scene 1.1 - 初见
label scene_1_1:
    scene bg_library_morning
    play music "bgm_peaceful.mp3"

    "阳光透过图书馆的窗户洒进来，空气中弥漫着纸张和墨水的味道。"

    show sakura neutral at center
    "一个女生正站在书架前，认真地整理书籍。"

    protagonist "那个...请问这本书可以借阅吗？"

    sakura "啊，当然可以。"

    "她转过身来，嘴角带着一丝微笑。樱色的发丝在阳光下泛着柔和的光。"

    sakura "对不起，我没注意到你。既然要借书，我帮你登记吧。"

    "小林的心微微一动，点了点头走向柜台。"
`,
  's1-2': `# Scene 1.2 - 借书
label scene_1_2:
    scene bg_library_counter
    play music "bgm_peaceful.mp3"

    sakura "请出示一下学生证。"

    protagonist "给你。"

    "小林将学生证递给她，她在登记册上记录。"

    sakura "《挪威的森林》...森下先生也喜欢村上春树吗？"

    protagonist "嗯，我才刚开始看，你呢？"

    sakura "这是我最喜欢的书之一，每次读都会有新的感受。"

    "两人目光短暂交汇，小林有些不好意思地移开视线。"
`,
  's1-3': `# Scene 1.3 - 告别
label scene_1_3:
    scene bg_library_entrance
    play music "bgm_peaceful.mp3"

    sakura "书已经登记好了，记得在闭馆前归还。"

    protagonist "谢谢你。对了，还不知道你的名字。"

    show sakura neutral at center
    sakura "我...我叫樱，是这里的图书管理员。"

    protagonist "樱...很好听的名字。我叫小林，刚转学过来。"

    # TODO: 这句台词需要修改 - 应该是微笑而不是拘谨
    sakura "转学...想必之前没来过这里吧？"

    "她露出一个淡淡的笑容。"

    sakura "欢迎常来图书馆，以后见。"
`,
  's2-1': `# Scene 2.1 - 招募
label scene_2_1:
    scene bg_club_room
    play music "bgm_peaceful.mp3"

    "放学后，小林和樱不约而同地来到文学社的招募摊位。"

    show sakura neutral at center
    sakura "咦，你也对这个社团感兴趣？"

    protagonist "嗯，正好空闲时间多，想多认识些人。"

    sakura "那太好了。我们是社团的创始成员之一，虽然人数不多，但大家都很热情。"
`,
  's2-2': `# Scene 2.2 - 合作
label scene_2_2:
    scene bg_club_room
    play music "bgm_peaceful.mp3"

    sakura "社团活动的第一项任务，就是一起准备下期文化祭的绘本展览。"

    protagonist "听起来很有意思，要我负责什么？"

    sakura "你负责整理封面文案，我负责排版和装订。一起加油！"

    "忙碌中，两人时常交换着笑容。"

    protagonist "有劳了。"
`,
  's3-1': `# Scene 3.1 - 犹豫
label scene_3_1:
    scene bg_sakura_tree
    play music "bgm_tension.mp3"

    "夕阳将天台染成橙红色，樱站在他身边，欲言又止。"

    protagonist "樱，我有话想对你说。"

    sakura "我...我也是。"

    menu:
        "鼓起勇气告白":
            jump scene_3_2a
        "把话咽回去":
            jump scene_3_2b
`,
  's3-2a': `# Scene 3.2a - 决心·告白线
label scene_3_2a:
    scene bg_sakura_tree
    play music "bgm_tension.mp3"

    protagonist "我喜欢你。从第一次见面开始，就喜欢上了。"

    show sakura happy at center
    sakura "笨蛋...我也等这句话很久了。"
`,
  's3-2b': `# Scene 3.2b - 决心·友情线
label scene_3_2b:
    scene bg_sakura_tree
    play music "bgm_peaceful.mp3"

    protagonist "那个...社团活动记得通知我。"

    sakura "当然，我们永远是好朋友。"
`,
};

const statusConfig = {
  pending: { label: '待生成', className: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400' },
  generating: { label: '生成中', className: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' },
  generated: { label: '已生成', className: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' },
  confirmed: { label: '已确认', className: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400' },
  audit_fail: { label: '审计失败', className: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' },
};

function parseScript(raw: string) {
  const lines = raw.split('\n');
  return lines.map((line) => {
    const trimmed = line.trim();
    if (trimmed.startsWith('#')) {
      return { type: 'other', content: trimmed.slice(1).trim(), raw: line } as const;
    }
    if (trimmed.startsWith('label ')) {
      return { type: 'label', content: trimmed.replace('label ', '').replace(':', ''), raw: line } as const;
    }
    if (trimmed.startsWith('menu:')) {
      return { type: 'menu', content: '', raw: line } as const;
    }
    if (trimmed.startsWith('"') && trimmed.endsWith('"')) {
      return { type: 'narration', content: trimmed.slice(1, -1), raw: line } as const;
    }
    if (/^\w+\s+"/.test(trimmed)) {
      const speaker = trimmed.split(' ')[0];
      const content = trimmed.slice(speaker.length + 2, -1);
      return { type: 'dialogue', speaker, content, raw: line } as const;
    }
    if (trimmed.startsWith('jump ')) {
      return { type: 'jump', content: trimmed.replace('jump ', ''), raw: line } as const;
    }
    if (trimmed.startsWith('scene ') || trimmed.startsWith('show ') || trimmed.startsWith('play ') || trimmed.startsWith('hide ')) {
      return { type: 'other', content: trimmed, raw: line } as const;
    }
    if (trimmed.startsWith('"') && trimmed.endsWith('":')) {
      return { type: 'choice', content: trimmed.slice(1, -2), raw: line } as const;
    }
    return { type: 'other', content: trimmed, raw: line } as const;
  });
}

export function SceneView({ onEdit }: { onEdit?: () => void }) {
  void onEdit;
  const { selectedSceneId, chapters, updateSceneStatus, jumpToScene } = useAppStore();
  const [activeTab, setActiveTab] = useState<'visual' | 'raw'>('visual');

  const scene = useMemo(() => {
    for (const ch of chapters) {
      const s = ch.scenes.find((sc: Scene) => sc.id === selectedSceneId);
      if (s) return s;
    }
    return null;
  }, [selectedSceneId, chapters]);

  const chapterName = useMemo(() => {
    for (const ch of chapters) {
      if (ch.scenes.some((sc: Scene) => sc.id === selectedSceneId)) {
        return ch.name;
      }
    }
    return '';
  }, [selectedSceneId, chapters]);

  const rawScript = scene ? mockScripts[scene.id] || `# Scene ${scene.id} - ${scene.name}\n# 脚本正在生成中...\n` : '';
  const parsed = useMemo(() => parseScript(rawScript), [rawScript]);

  const nextScenes = useMemo(() => {
    const resolveSceneName = (sceneId: string) => {
      for (const ch of chapters) {
        const s = ch.scenes.find((sc: Scene) => sc.id === sceneId);
        if (s) return s.name;
      }
      return sceneId;
    };
    const findSceneIdByLabel = (label: string) => {
      for (const ch of chapters) {
        const s = ch.scenes.find((sc: Scene) => sc.id === label || sc.name === label);
        if (s) return s.id;
      }
      return label;
    };

    if (scene?.choices?.length) {
      return scene.choices.map((choice) => ({
        label: choice.text,
        sceneId: choice.nextSceneId,
        sceneName: resolveSceneName(choice.nextSceneId),
      }));
    }
    const lastChoice = parsed.filter((l) => l.type === 'choice');
    if (lastChoice.length > 0) {
      return lastChoice.map((choice) => {
        const rawContent = choice.raw.trim();
        const text = rawContent.slice(1, rawContent.lastIndexOf('":'));
        const targetLine = parsed[parsed.indexOf(choice) + 1];
        let target = '';
        if (targetLine && targetLine.type === 'jump') {
          target = targetLine.content;
        }
        return {
          label: text,
          sceneId: findSceneIdByLabel(target),
          sceneName: resolveSceneName(findSceneIdByLabel(target)),
        };
      });
    }
    return [];
  }, [scene, parsed, chapters]);

  if (!scene) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50 dark:bg-gray-950 p-8">
        <div className="text-center">
          <div className="w-16 h-16 rounded-2xl bg-gray-100 dark:bg-gray-900 flex items-center justify-center mx-auto mb-4">
            <Code className="w-8 h-8 text-gray-400" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
            未选择场景
          </h3>
          <p className="text-sm text-gray-500">
            请在左侧 Timeline 中选择一个 Scene 查看详情
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto bg-white dark:bg-gray-950">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-white/90 dark:bg-gray-950/90 backdrop-blur border-b border-gray-200 dark:border-gray-800 px-6 py-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                {chapterName} · Scene {scene.id}
              </h2>
              <Badge className={cn('border-0', statusConfig[scene.status].className)}>
                {statusConfig[scene.status].label}
              </Badge>
            </div>
            <p className="text-sm text-gray-500">
              {scene.characters?.join('、')} · {scene.backgrounds?.join('、')} · {scene.endingName || (scene.type === 'ending' ? '结局' : scene.type === 'branch_point' ? '分支点' : '普通场景')}
            </p>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'visual' | 'raw')}>
              <TabsList className="h-9">
                <TabsTrigger value="visual" className="text-xs px-3">可视化</TabsTrigger>
                <TabsTrigger value="raw" className="text-xs px-3">原始脚本</TabsTrigger>
              </TabsList>
            </Tabs>
            <Button variant="outline" size="sm" className="gap-1" disabled title="功能开发中">
              <Play className="w-4 h-4" />
              试玩
            </Button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="px-6 py-6 space-y-6">
        {/* Action Bar */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {scene.status !== 'confirmed' && (
              <Button
                size="sm"
                className="gap-1"
                onClick={() => updateSceneStatus(scene.id, 'confirmed')}
              >
                <CheckCircle2 className="w-4 h-4" />
                确认场景
              </Button>
            )}
            {scene.status === 'confirmed' && (
              <Button
                variant="outline"
                size="sm"
                className="gap-1"
                onClick={() => updateSceneStatus(scene.id, 'generated')}
              >
                <RefreshCw className="w-4 h-4" />
                重新生成
              </Button>
            )}
          </div>

          <div className="text-xs text-gray-500">
            上次更新: 2026-04-15
          </div>
        </div>

        {activeTab === 'visual' ? (
          <>
            {/* Visual Script */}
            <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-900/50 p-5 space-y-4">
              {parsed.map((line, idx) => {
                if (line.type === 'narration') {
                  return (
                    <p key={idx} className="text-gray-600 dark:text-gray-400 italic leading-relaxed">
                      {line.content}
                    </p>
                  );
                }
                if (line.type === 'dialogue') {
                  const isProtagonist = line.speaker === 'protagonist';
                  return (
                    <div key={idx} className={cn(
                      "flex gap-3",
                      isProtagonist && "flex-row-reverse"
                    )}>
                      <div className={cn(
                        "w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0",
                        isProtagonist ? "bg-blue-100 dark:bg-blue-900/30" : "bg-pink-100 dark:bg-pink-900/30"
                      )}>
                        <User className={cn(
                          "w-5 h-5",
                          isProtagonist ? "text-blue-500" : "text-pink-500"
                        )} />
                      </div>
                      <div className={cn(
                        "flex-1 max-w-[80%]",
                        isProtagonist && "text-right"
                      )}>
                        <p className="text-xs text-gray-500 mb-1">
                          {isProtagonist ? '小林' : line.speaker === 'sakura' ? '樱' : line.speaker}
                        </p>
                        <div className={cn(
                          "inline-block px-4 py-2 rounded-2xl text-left",
                          isProtagonist
                            ? "bg-blue-500 text-white"
                            : "bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700"
                        )}>
                          <p className={cn("text-sm", !isProtagonist && "text-gray-800 dark:text-gray-200")}>
                            {line.content}
                          </p>
                        </div>
                      </div>
                    </div>
                  );
                }
                if (line.type === 'choice') {
                  return (
                    <div key={idx} className="my-2 p-3 rounded-lg bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-800">
                      <div className="flex items-center gap-2 text-purple-700 dark:text-purple-400">
                        <GitFork className="w-4 h-4" />
                        <span className="text-sm font-medium">分支选项: {line.content}</span>
                      </div>
                    </div>
                  );
                }
                if (line.type === 'label') {
                  return (
                    <div key={idx} className="pt-2">
                      <Badge variant="outline" className="text-xs font-mono">
                        {line.content}
                      </Badge>
                    </div>
                  );
                }
                if (line.type === 'other' && line.content.startsWith('scene ')) {
                  return (
                    <div key={idx} className="flex items-center gap-2 text-sm text-gray-500 py-1">
                      <Image className="w-4 h-4" />
                      <span>场景切换: {line.content.replace('scene ', '')}</span>
                    </div>
                  );
                }
                if (line.type === 'other' && line.content.startsWith('play music')) {
                  return (
                    <div key={idx} className="flex items-center gap-2 text-sm text-gray-500 py-1">
                      <Music className="w-4 h-4" />
                      <span>播放音乐: {line.content.match(/"(.+?)"/)?.[1] || ''}</span>
                    </div>
                  );
                }
                return null;
              })}
            </div>

            {/* Scene Meta */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Resources */}
              <div className="p-4 rounded-xl border border-gray-200 dark:border-gray-800">
                <h4 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">场景资源</h4>
                <div className="space-y-2">
                  {scene.backgrounds?.map((bg, i) => (
                    <div key={i} className="flex items-center gap-3 p-2 rounded-lg bg-gray-50 dark:bg-gray-900">
                      <Image className="w-4 h-4 text-blue-500" />
                      <span className="text-sm text-gray-700 dark:text-gray-300">{bg}</span>
                    </div>
                  ))}
                  {scene.music && (
                    <div className="flex items-center gap-3 p-2 rounded-lg bg-gray-50 dark:bg-gray-900">
                      <Music className="w-4 h-4 text-purple-500" />
                      <span className="text-sm text-gray-700 dark:text-gray-300">{scene.music}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Flow */}
              <div>
                <h4 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">剧情流向</h4>
                {scene.type === 'ending' || scene.isEnding ? (
                  <div className="p-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 text-center">
                    <div className="text-2xl mb-1">🎉</div>
                    <p className="text-sm font-medium text-amber-800 dark:text-amber-300">结局达成</p>
                    <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                      {scene.endingName || ''}
                    </p>
                  </div>
                ) : nextScenes.length > 0 ? (
                  <div className="space-y-2">
                    {nextScenes.map((ns, idx) => (
                      <Button
                        key={idx}
                        variant="outline"
                        size="sm"
                        className="w-full justify-between h-auto py-2 px-2.5"
                        onClick={() => ns.sceneId && jumpToScene(ns.sceneId)}
                      >
                        <span className="flex items-center gap-2">
                          <GitFork className="w-4 h-4 text-purple-500" />
                          <span className="text-sm font-medium">{ns.label}</span>
                        </span>
                        <span className="flex items-center gap-1 text-xs text-gray-500">
                          {ns.sceneName}
                          <ArrowRight className="w-3 h-3" />
                        </span>
                      </Button>
                    ))}
                  </div>
                ) : (
                  <div className="p-3 rounded-lg bg-gray-50 dark:bg-gray-900 text-center text-sm text-gray-500">
                    无后续分支，继续下一幕
                  </div>
                )}
              </div>
            </div>
          </>
        ) : (
          <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-950 p-5 overflow-x-auto">
            <pre className="text-sm font-mono text-gray-300 whitespace-pre">
              {rawScript}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
