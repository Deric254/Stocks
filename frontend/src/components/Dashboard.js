import React, { useEffect, useState } from "react";
import { getSummary } from "../services/api";
import Charts from "./Charts";

function Dashboard() {
  const [summary, setSummary] = useState(null);

  useEffect(() => {
    loadSummary();
  }, []);

  const loadSummary = async () => {
    const res = await getSummary();
    setSummary(res.data);
  };

  if (!summary) return <p>Loading...</p>;

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid md:grid-cols-4 gap-6">
        <div className="bg-white p-6 rounded-xl shadow">
          <p className="text-gray-500">Total Invested</p>
          <h3 className="text-xl font-bold text-blue-800">
            ${summary.total_invested.toFixed(2)}
          </h3>
        </div>

        <div className="bg-white p-6 rounded-xl shadow">
          <p className="text-gray-500">Current Value</p>
          <h3 className="text-xl font-bold text-blue-800">
            ${summary.current_value.toFixed(2)}
          </h3>
        </div>

        <div className="bg-white p-6 rounded-xl shadow">
          <p className="text-gray-500">Unrealized Profit</p>
          <h3
            className={`text-xl font-bold ${
              summary.unrealized_profit >= 0
                ? "text-green-500"
                : "text-red-500"
            }`}
          >
            ${summary.unrealized_profit.toFixed(2)}
          </h3>
        </div>

        <div className="bg-white p-6 rounded-xl shadow">
          <p className="text-gray-500">Realized Profit</p>
          <h3
            className={`text-xl font-bold ${
              summary.realized_profit >= 0
                ? "text-green-500"
                : "text-red-500"
            }`}
          >
            ${summary.realized_profit.toFixed(2)}
          </h3>
        </div>
      </div>

      {/* Chart */}
      <Charts />
    </div>
  );
}

export default Dashboard;