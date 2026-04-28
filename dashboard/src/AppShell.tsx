import { cn } from "@/lib/utils";
import { Menu, MessageSquare, PanelRightClose, PanelRightOpen, Sparkles, X } from "lucide-react";
import { useState, useEffect } from "react";
import { useLocation } from "react-router-dom";
import { ChatDrawer } from "./components/ChatDrawer";

interface AppShellProps {
  children: React.ReactNode;
  className?: string;
}

export function AppShell({ children, className }: AppShellProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatDockCollapsed, setChatDockCollapsed] = useState(false);
  const [isDesktop, setIsDesktop] = useState(() => {
    if (typeof window !== "undefined") {
      return window.innerWidth >= 1024;
    }
    return true;
  });
  const location = useLocation();

  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const handler = (e: MediaQueryListEvent) => setIsDesktop(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  useEffect(() => {
    const openHandler = () => setChatOpen(true);
    const closeHandler = () => setChatOpen(false);
    window.addEventListener("open-chat-drawer", openHandler);
    window.addEventListener("close-chat-drawer", closeHandler);
    return () => {
      window.removeEventListener("open-chat-drawer", openHandler);
      window.removeEventListener("close-chat-drawer", closeHandler);
    };
  }, []);

  // Dashboard routes hide the legacy sidebar entirely
  const isProjectListRoute = location.pathname === "/projects";
  const isWorkspaceRoute = location.pathname.startsWith("/projects/");
  const isDashboardRoute = isProjectListRoute || isWorkspaceRoute;
  const showAI = !isProjectListRoute;

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background text-foreground">
      {/* Mobile sidebar overlay (only for non-dashboard legacy routes) */}
      {sidebarOpen && !isDashboardRoute && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Legacy sidebar — hidden on all dashboard routes */}
      {!isDashboardRoute && (
        <aside
          className={cn(
            "fixed inset-y-0 left-0 z-50 w-64 border-r bg-card transition-transform lg:static lg:translate-x-0",
            sidebarOpen ? "translate-x-0" : "-translate-x-full"
          )}
        >
          <div className="flex h-14 items-center border-b px-4">
            <Sparkles className="mr-2 h-5 w-5" />
            <span className="font-semibold">RenPy MCP</span>
            <button
              className="ml-auto lg:hidden"
              onClick={() => setSidebarOpen(false)}
              aria-label="Close sidebar"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
          <nav className="space-y-1 p-3">
            {/* Legacy navigation removed from main shell.
                Only a back-to-home link remains for non-dashboard pages. */}
            <a
              href="/dashboard/projects"
              className="flex items-center rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground"
            >
              ← 回到项目列表
            </a>
          </nav>
        </aside>
      )}

      {/* Main content */}
      <div className="flex flex-1 flex-col min-w-0">
        {/* Top bar — minimal on dashboard routes */}
        <header className="flex h-14 items-center border-b bg-card px-4">
          {!isDashboardRoute && (
            <button
              className="mr-4 lg:hidden"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open sidebar"
            >
              <Menu className="h-5 w-5" />
            </button>
          )}
          <div className="flex-1" />
          <div className="flex items-center gap-3">
            {showAI && (
              <button
                onClick={() => setChatOpen(true)}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-accent",
                  isWorkspaceRoute && "lg:hidden"
                )}
              >
                <MessageSquare className="h-4 w-4" />
                AI 助手
              </button>
            )}
            <span className="text-sm text-muted-foreground">v0.1.0</span>
          </div>
        </header>

        {/* Page content */}
        <main
          className={cn(
            "flex-1 overflow-auto",
            isDashboardRoute ? "p-0" : "p-4",
            className
          )}
        >
          {children}
        </main>
      </div>

      {/* Desktop persistent AI panel for workspace routes only */}
      {isWorkspaceRoute && isDesktop && (
        <div
          data-testid="workspace-chat-dock"
          className={cn(
            "relative h-full flex-shrink-0 border-l bg-slate-50/70 transition-[width] duration-200",
            chatDockCollapsed ? "w-12" : "w-[320px]"
          )}
        >
          {chatDockCollapsed ? (
            <button
              type="button"
              aria-label="Expand AI assistant"
              title="Expand AI assistant"
              onClick={() => setChatDockCollapsed(false)}
              className="flex h-14 w-full items-center justify-center border-b text-slate-700 hover:bg-white"
            >
              <PanelRightOpen className="h-4 w-4" />
            </button>
          ) : (
            <>
              <button
                type="button"
                aria-label="Collapse AI assistant"
                title="Collapse AI assistant"
                onClick={() => setChatDockCollapsed(true)}
                className="absolute right-3 top-3 z-10 inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-900"
              >
                <PanelRightClose className="h-4 w-4" />
              </button>
              <ChatDrawer mode="docked" />
            </>
          )}
        </div>
      )}

      {/* Overlay drawer: workspace mobile + legacy routes (homepage excluded) */}
      {showAI && (!isWorkspaceRoute || !isDesktop) && (
        <ChatDrawer open={chatOpen} onClose={() => setChatOpen(false)} mode="overlay" />
      )}
    </div>
  );
}
