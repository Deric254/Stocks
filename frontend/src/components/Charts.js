import React, { useEffect, useState } from "react";
import { getPositions } from "../services/api";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer
} from "recharts";

function Charts() {
  const [data, setData] = useState([]);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    const res = await getPositions();
    const formatted = res.data.map((pos) => ({
      name: pos.ticker,
      pnl: pos.pnl
    }));
    setData(formatted);
  };

  return (
    <div className="bg-white p-6 rounded-xl shadow h-96">
      <h3 className="text-lg font-semibold mb-4 text-blue-800">
        Portfolio Performance
      </h3>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <XAxis dataKey="name" />
          <YAxis />
          <Tooltip />
          <Line
            type="monotone"
            dataKey="pnl"
            stroke="#3B82F6"
            strokeWidth={3}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default Charts;