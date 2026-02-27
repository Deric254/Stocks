import React, { useEffect, useState } from "react";
import { getPositions, sellStock } from "../services/api";

function Portfolio() {
  const [positions, setPositions] = useState([]);

  useEffect(() => {
    loadPositions();
  }, []);

  const loadPositions = async () => {
    const res = await getPositions();
    setPositions(res.data);
  };

  const handleSell = async (id) => {
    await sellStock(id);
    loadPositions();
  };

  return (
    <div>
      <table className="w-full bg-white shadow rounded-xl overflow-hidden">
        <thead className="bg-blue-800 text-white">
          <tr>
            <th className="p-3">Ticker</th>
            <th>Quantity</th>
            <th>Buy Price</th>
            <th>Current Price</th>
            <th>P/L</th>
            <th>Sell</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((pos, index) => (
            <tr key={index} className="border-b text-center">
              <td>{pos.ticker}</td>
              <td>{pos.quantity}</td>
              <td>${pos.buy_price}</td>
              <td>${pos.current_price?.toFixed(2)}</td>
              <td
                className={`font-bold ${
                  pos.pnl >= 0 ? "text-green-500" : "text-red-500"
                }`}
              >
                ${pos.pnl.toFixed(2)}
              </td>
              <td>
                <button
                  onClick={() => handleSell(pos.id)}
                  className="bg-red-500 text-white px-3 py-1 rounded"
                >
                  Sell
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default Portfolio;