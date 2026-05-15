import { NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Plug,
  ShieldAlert,
  BookOpen,
  Users,
  Settings,
  Sun,
  Moon,
  AppWindow,
  ChevronsLeft,
  ChevronsRight,
  ClipboardList,
} from 'lucide-react'
import { useState, useEffect } from 'react'

interface NavItem {
  to: string
  label: string
  icon: React.ReactNode
}

const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: <LayoutDashboard size={16} /> },
  { to: '/connectors', label: 'Connectors', icon: <Plug size={16} /> },
  { to: '/findings', label: 'Findings', icon: <ShieldAlert size={16} /> },
  { to: '/third-party-apps', label: 'Third-Party Apps', icon: <AppWindow size={16} /> },
  { to: '/compliance', label: 'Compliance', icon: <ClipboardList size={16} /> },
  { to: '/rules', label: 'Rules', icon: <BookOpen size={16} /> },
  { to: '/identities', label: 'SaaS Identities', icon: <Users size={16} /> },
  { to: '/settings', label: 'Settings', icon: <Settings size={16} /> },
]

const SIDEBAR_EXPANDED_W = '220px'
const SIDEBAR_COLLAPSED_W = '64px'

export default function Sidebar() {
  const location = useLocation()

  const [dark, setDark] = useState<boolean>(() => {
    try {
      return (
        localStorage.getItem('sspm-theme') === 'dark' ||
        (!localStorage.getItem('sspm-theme') &&
          globalThis.matchMedia('(prefers-color-scheme: dark)').matches)
      )
    } catch {
      return false
    }
  })

  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem('sspm-sidebar') === 'collapsed'
    } catch {
      return false
    }
  })

  useEffect(() => {
    const theme = dark ? 'dark' : 'light'
    document.documentElement.dataset.theme = theme
    document.documentElement.classList.toggle('dark', dark)
    localStorage.setItem('sspm-theme', theme)
  }, [dark])

  useEffect(() => {
    const w = collapsed ? SIDEBAR_COLLAPSED_W : SIDEBAR_EXPANDED_W
    document.documentElement.style.setProperty('--sidebar-w', w)
    localStorage.setItem('sspm-sidebar', collapsed ? 'collapsed' : 'expanded')
  }, [collapsed])

  const themeLabel = dark ? 'Light mode' : 'Dark mode'

  return (
    <aside className={`sidebar${collapsed ? ' collapsed' : ''}`}>
      {/* Nav */}
      <nav className="sidebar-nav">
        {NAV_ITEMS.map(({ to, label, icon }) => {
          const isActive =
            to === '/' ? location.pathname === '/' : location.pathname.startsWith(to)
          return (
            <NavLink
              key={to}
              to={to}
              className={`nav-item${isActive ? ' is-active' : ''}`}
              title={collapsed ? label : undefined}
            >
              <span className="nav-icon">{icon}</span>
              <span className="nav-label">{label}</span>
            </NavLink>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="sidebar-footer">
        <button
          onClick={() => setCollapsed((c) => !c)}
          className="nav-item"
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          title={collapsed ? 'Expand sidebar' : undefined}
          style={{ width: '100%' }}
        >
          <span className="nav-icon">
            {collapsed ? <ChevronsRight size={16} /> : <ChevronsLeft size={16} />}
          </span>
          <span className="nav-label">Collapse</span>
        </button>
        <button
          onClick={() => setDark((d) => !d)}
          className="nav-item"
          aria-label="Toggle theme"
          title={collapsed ? themeLabel : undefined}
          style={{ width: '100%' }}
        >
          <span className="nav-icon">
            {dark ? <Sun size={16} /> : <Moon size={16} />}
          </span>
          <span className="nav-label">{dark ? 'Light mode' : 'Dark mode'}</span>
        </button>
      </div>
    </aside>
  )
}
