import { useAppStore } from '@/store/useAppStore';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Sparkles, FileText, Wand2, Lightbulb, Loader2 } from 'lucide-react';

export function OnboardingView() {
  const { blueprintPhase, startBlueprintCollection, createEmptyBlueprint } = useAppStore();

  const isActive = blueprintPhase === 'collecting' || blueprintPhase === 'reviewing';

  return (
    <div className="h-full overflow-y-auto p-8 flex items-center justify-center bg-gray-50/50 dark:bg-gray-900/50">
      <Card className="max-w-xl w-full">
        <CardContent className="p-8 text-center">
          {isActive ? (
            <>
              <div className="w-16 h-16 rounded-2xl bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center mx-auto mb-6">
                <Loader2 className="w-8 h-8 text-blue-600 dark:text-blue-400 animate-spin" />
              </div>

              <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                正在与 AI 细化需求...
              </h2>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
                你可以在右侧 Chat 面板中继续补充想法。AI 会根据你的描述生成蓝图。
              </p>

              <div className="text-left bg-gray-50 dark:bg-gray-800/50 rounded-xl p-4">
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  💡 小贴士：尽量描述你想要的章节数、主角人设、故事基调以及是否需要分支结局，这样生成的蓝图会更符合预期。
                </p>
              </div>
            </>
          ) : (
            <>
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500 to-purple-500 flex items-center justify-center mx-auto mb-6">
                <Sparkles className="w-8 h-8 text-white" />
              </div>

              <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                项目已创建，开始构建蓝图吧
              </h2>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-8">
                蓝图是整个视觉小说的骨架。你可以让 AI 自动生成，也可以手动编辑 YAML。
              </p>

              <div className="flex flex-col sm:flex-row gap-3 justify-center mb-8">
                <Button size="lg" className="gap-2 flex-1" onClick={startBlueprintCollection}>
                  <Wand2 className="w-4 h-4" />
                  让 AI 生成蓝图
                </Button>
                <Button size="lg" variant="outline" className="gap-2 flex-1" onClick={createEmptyBlueprint}>
                  <FileText className="w-4 h-4" />
                  手动编辑 YAML
                </Button>
              </div>

              <div className="text-left bg-gray-50 dark:bg-gray-800/50 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Lightbulb className="w-4 h-4 text-yellow-500" />
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
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
        </CardContent>
      </Card>
    </div>
  );
}

function ExamplePill({ text }: { text: string }) {
  return (
    <span className="inline-block px-3 py-1.5 text-xs rounded-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400">
      {text}
    </span>
  );
}
