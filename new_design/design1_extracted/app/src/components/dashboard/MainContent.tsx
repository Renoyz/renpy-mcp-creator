import { useAppStore } from '@/store/useAppStore';
import { BlueprintView } from './BlueprintView';
import { ScriptEditor } from './ScriptEditor';
import { AuditReportView } from './AuditReportView';
import { ResourcesView } from './ResourcesView';
import { StoryMapView } from './StoryMapView';
import { SceneView } from './SceneView';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { FileText, Map, ClipboardCheck, Code, Image, AlertCircle, ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useState } from 'react';

export function MainContent() {
  const { activeTab, setActiveTab, selectedSceneId, setSelectedScene } = useAppStore();
  const [isEditingScript, setIsEditingScript] = useState(false);
  const isSceneSelected = !!selectedSceneId;

  return (
    <div className="h-full flex flex-col bg-white dark:bg-gray-950">
      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-800 flex items-center justify-between">
        {isSceneSelected ? (
          <>
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <TabsList className="w-full justify-start rounded-none bg-transparent border-b-0 p-0 h-12">
                <TabsTrigger
                  value="script"
                  className={cn(
                    "rounded-none border-b-2 border-transparent data-[state=active]:border-blue-500 data-[state=active]:bg-transparent data-[state=active]:shadow-none px-4 gap-2"
                  )}
                >
                  <Code className="w-4 h-4" />
                  脚本
                </TabsTrigger>
                <TabsTrigger
                  value="resources"
                  className={cn(
                    "rounded-none border-b-2 border-transparent data-[state=active]:border-blue-500 data-[state=active]:bg-transparent data-[state=active]:shadow-none px-4 gap-2"
                  )}
                >
                  <Image className="w-4 h-4" />
                  资源
                </TabsTrigger>
                <TabsTrigger
                  value="audit"
                  className={cn(
                    "rounded-none border-b-2 border-transparent data-[state=active]:border-blue-500 data-[state=active]:bg-transparent data-[state=active]:shadow-none px-4 gap-2"
                  )}
                >
                  <AlertCircle className="w-4 h-4" />
                  审计
                </TabsTrigger>
              </TabsList>
            </Tabs>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setSelectedScene(null);
                setActiveTab('blueprint');
              }}
              className="gap-2 mr-4 text-gray-600 dark:text-gray-400"
            >
              <ArrowLeft className="w-4 h-4" />
              返回概览
            </Button>
          </>
        ) : (
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="w-full justify-start rounded-none bg-transparent border-b-0 p-0 h-12">
              <TabsTrigger
                value="blueprint"
                className={cn(
                  "rounded-none border-b-2 border-transparent data-[state=active]:border-blue-500 data-[state=active]:bg-transparent data-[state=active]:shadow-none px-4 gap-2"
                )}
              >
                <FileText className="w-4 h-4" />
                蓝图
              </TabsTrigger>
              <TabsTrigger
                value="storymap"
                className={cn(
                  "rounded-none border-b-2 border-transparent data-[state=active]:border-blue-500 data-[state=active]:bg-transparent data-[state=active]:shadow-none px-4 gap-2"
                )}
              >
                <Map className="w-4 h-4" />
                Story Map
              </TabsTrigger>
              <TabsTrigger
                value="audit"
                className={cn(
                  "rounded-none border-b-2 border-transparent data-[state=active]:border-blue-500 data-[state=active]:bg-transparent data-[state=active]:shadow-none px-4 gap-2"
                )}
              >
                <ClipboardCheck className="w-4 h-4" />
                审计报告
              </TabsTrigger>
            </TabsList>
          </Tabs>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {isSceneSelected ? (
          <>
            {activeTab === 'script' && (
              isEditingScript ? <ScriptEditor onBack={() => setIsEditingScript(false)} /> : <SceneView onEdit={() => setIsEditingScript(true)} />
            )}
            {activeTab === 'resources' && <ResourcesView />}
            {activeTab === 'audit' && <AuditReportView />}
          </>
        ) : (
          <>
            {activeTab === 'blueprint' && <BlueprintView />}
            {activeTab === 'storymap' && <StoryMapView />}
            {activeTab === 'audit' && <AuditReportView />}
          </>
        )}
      </div>
    </div>
  );
}
