import React from "react";
import { BrowserRouter as Router, Routes, Route, Link } from "react-router-dom";
import { motion } from "framer-motion";
import { FaChartLine, FaList, FaWallet } from "react-icons/fa";

import Dashboard from "./components/Dashboard";
import Watchlist from "./components/Watchlist";
import Portfolio from "./components/Portfolio";

function App() {
  return (
    <Router>
      <div className="flex h-screen bg-gray-50">
        
        {/* Sidebar */}
        <div className="w-64 bg-blue-800 text-white p-5 hidden md:block">
          <h1 className="text-2xl font-bold mb-8">DericBI Stock Vantage</h1>
          <nav className="space-y-4">
            <Link to="/" className="flex items-center gap-2 hover:text-green-400">
              <FaChartLine /> Dashboard
            </Link>
            <Link to="/watchlist" className="flex items-center gap-2 hover:text-green-400">
              <FaList /> Watchlist
            </Link>
            <Link to="/portfolio" className="flex items-center gap-2 hover:text-green-400">
              <FaWallet /> Portfolio
            </Link>
          </nav>
        </div>

        {/* Main Content */}
        <div className="flex-1 overflow-y-auto">
          {/* Top Bar */}
          <div className="bg-white shadow p-4 flex justify-between items-center">
            <h2 className="text-xl font-semibold text-blue-800">
              DericBI Stock Vantage
            </h2>
            <span className="text-sm text-gray-500">
              Value Investing • Nyoro Strategy
            </span>
          </div>

          {/* Pages */}
          <div className="p-6">
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
            >
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/watchlist" element={<Watchlist />} />
                <Route path="/portfolio" element={<Portfolio />} />
              </Routes>
            </motion.div>
          </div>
        </div>

      </div>
    </Router>
  );
}

export default App;