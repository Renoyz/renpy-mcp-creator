import { cn } from "@/lib/utils";
import { Menu, X, Layers, MessageSquare } from "lucide-react";
import { useState } from "react";
import { NavLink } from "react-router-dom";
import { ChatDrawer } from "./components/ChatDrawer";

interface AppShellProps {
  children: React.ReactNode;
  className?: string;
}

const navItems = [
  { label: "项目", to: "/projects" },
  { label: "Story Map", to: "/story-map" },
  { label: "脚本编辑", to: "/script-editor" },
  { label: "资源管理", to: "/assets" },
];

export function AppShell({ children, className }: AppShellProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background text-foreground">
      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 w-64 border-r bg-card transition-transform lg:static lg:translate-x-0",
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="flex h-14 items-center border-b px-4">
          <Layers className="mr-2 h-5 w-5" />
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
          {navItems.map((item) => (
            <NavLink
              key={item.label}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground",
                  isActive && "bg-accent text-accent-foreground"
                )
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      {/* Main content */}
      <div className="flex flex-1 flex-col min-w-0">
        {/* Top bar */}
        <header className="flex h-14 items-center border-b bg-card px-4">
          <button
            className="mr-4 lg:hidden"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open sidebar"
          >
            <Menu className="h-5 w-5" />
          </button>
          <div className="flex-1" />
          <div className="flex items-center gap-3">
            <button
              onClick={() => setChatOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-accent"
            >
              <MessageSquare className="h-4 w-4" />
              AI 助手
            </button>
            <span className="text-sm text-muted-foreground">v0.1.0</span>
          </div>
        </header>

        {/* Page content */}
        <main className={cn("flex-1 overflow-auto p-4", className)}>
          {children}
        </main>
      </div>

      <ChatDrawer open={chatOpen} onClose={() => setChatOpen(false)} />
    </div>
  );
}
