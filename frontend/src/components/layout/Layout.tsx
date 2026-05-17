import { Outlet } from 'react-router-dom'
import Header from './Header'
import Sidebar from './Sidebar'
import Topbar from './Topbar'
import { SSPMerChat } from '../SSPMerChat'

export default function Layout() {
  return (
    <>
      <Header />
      <div className="app">
        <Sidebar />
        <div className="main-content">
          <Topbar />
          <main className="page">
            <Outlet />
          </main>
        </div>
      </div>
      <SSPMerChat />
    </>
  )
}
