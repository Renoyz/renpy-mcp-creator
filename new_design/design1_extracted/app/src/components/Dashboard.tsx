import { useAppStore } from '@/store/useAppStore';
import { ChapterTimeline } from './dashboard/ChapterTimeline';
import { MainContent } from './dashboard/MainContent';
import { OnboardingView } from './dashboard/OnboardingView';
import { GeneratingView } from './dashboard/GeneratingView';

export function Dashboard() {
  const { isGenerating, blueprint, chapters, blueprintPhase } = useAppStore();

  const renderCenter = () => {
    if (isGenerating || blueprintPhase === 'generating') {
      return <GeneratingView />;
    }
    if ((!blueprint || chapters.length === 0) && blueprintPhase !== 'editing') {
      return <OnboardingView />;
    }
    return <MainContent />;
  };

  return (
    <div className="flex-1 flex overflow-hidden">
      {/* Left: Chapter Timeline */}
      <div className="w-56 flex-shrink-0">
        <ChapterTimeline />
      </div>

      {/* Center: Main Content */}
      <div className="flex-1 min-w-0">
        {renderCenter()}
      </div>
    </div>
  );
}
