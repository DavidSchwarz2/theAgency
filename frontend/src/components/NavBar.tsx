import { NavLink } from 'react-router-dom'

export default function NavBar() {
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `px-4 py-2 rounded text-sm font-medium transition-colors ${
      isActive
        ? 'bg-gray-700 text-white'
        : 'text-gray-400 hover:text-white hover:bg-gray-800'
    }`

  return (
    <nav className="flex items-center gap-2 border-b border-gray-800 px-6 py-3 bg-gray-950">
      <span className="text-white font-mono font-bold mr-4">theAgency</span>
      <NavLink to="/" end className={linkClass}>
        Pipelines
      </NavLink>
      <NavLink to="/audit" className={linkClass}>
        Audit Trail
      </NavLink>
    </nav>
  )
}
