import { NavLink, Outlet } from "react-router-dom";
import { clsx } from "clsx";

import { useAppStore } from "../../store/app";
import { StatusDot } from "../ui";

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: "◧" },
  { to: "/projects", label: "Projects", icon: "▣" },
  { to: "/studio", label: "Studio", icon: "✦" },
  { to: "/runtime", label: "Runtime", icon: "⬢" },
  { to: "/lab", label: "Lab", icon: "⚗" },
  { to: "/settings", label: "Settings", icon: "⚙" },
];

function Logo() {
  return (
    <div className="flex items-center gap-2.5 px-4 py-5">
      <svg viewBox="0 0 32 32" className="h-7 w-7 shrink-0">
        <rect width="32" height="32" rx="7" fill="#13131a" />
        <g stroke="#6366f1" strokeWidth="1.8" fill="none">
          <path d="M9 11 L16 16 L9 21" />
          <path d="M16 16 L24 16" />
        </g>
        <circle cx="9" cy="11" r="3" fill="#818cf8" />
        <circle cx="9" cy="21" r="3" fill="#818cf8" />
        <circle cx="16" cy="16" r="3" fill="#a5b4fc" />
        <circle cx="24" cy="16" r="3" fill="#34d399" />
      </svg>
      <div>
        <div className="text-[15px] font-semibold tracking-tight text-zinc-100">AgentLab</div>
        <div className="text-[10px] font-medium uppercase tracking-wider text-zinc-600">
          agent observability
        </div>
      </div>
    </div>
  );
}

function ConnectionPill() {
  const wsStatus = useAppStore((s) => s.wsStatus);
  const styles = {
    live: { dot: "bg-emerald-400", label: "Live stream", pulse: true },
    connecting: { dot: "bg-amber-400", label: "Connecting…", pulse: false },
    offline: { dot: "bg-zinc-600", label: "No live stream", pulse: false },
  }[wsStatus];
  return (
    <div className="mx-3 mb-4 flex items-center gap-2 rounded-lg border border-edge bg-surface-2 px-3 py-2">
      <StatusDot className={styles.dot} pulse={styles.pulse} />
      <span className="text-[11px] font-medium text-zinc-400">{styles.label}</span>
    </div>
  );
}

export function Shell() {
  return (
    <div className="flex h-full">
      <aside className="flex w-56 shrink-0 flex-col border-r border-edge bg-surface-1">
        <Logo />
        <nav className="flex-1 space-y-0.5 px-3 pt-2">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors",
                  isActive
                    ? "bg-indigo-500/10 text-indigo-300"
                    : "text-zinc-400 hover:bg-surface-2 hover:text-zinc-200",
                )
              }
            >
              <span className="w-4 text-center text-[13px] opacity-80">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <ConnectionPill />
        <div className="border-t border-edge px-4 py-3 text-[10px] text-zinc-600">
          v1.1.0 · local mode
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[1500px] px-6 py-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
