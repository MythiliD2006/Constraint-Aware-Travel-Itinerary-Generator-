import { Bookmark, Network, Route as RouteIcon } from 'lucide-react'
import { NavLink } from 'react-router-dom'

const links = [
  { to: '/', label: 'Plan a trip', icon: RouteIcon, end: true },
  { to: '/saved', label: 'Saved', icon: Bookmark, end: false },
  { to: '/knowledge', label: 'Knowledge base', icon: Network, end: false },
]

export default function NavBar() {
  return (
    <header className="border-b border-line bg-paper">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6">
        <NavLink to="/" className="flex items-center gap-2.5 font-semibold text-forest-deep">
          <img src="/favicon.svg" alt="" className="h-7 w-7" />
          <span className="hidden sm:inline">HTN Itinerary Planner</span>
        </NavLink>
        <nav className="flex items-center gap-1" aria-label="Main">
          {links.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm transition-colors ${
                  isActive ? 'bg-forest-soft font-medium text-forest-deep' : 'text-muted hover:text-ink'
                }`
              }
            >
              <Icon size={16} aria-hidden />
              <span className="hidden sm:inline">{label}</span>
              <span className="sr-only sm:hidden">{label}</span>
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
  )
}
