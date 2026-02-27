import React, { useEffect, useState } from "react";
import { fetchStocks, refreshStocks, buyStock } from "../services/api";

function Watchlist() {
  const [stocks, setStocks] = useState([]);
  const [minScore, setMinScore] = useState(3);
  const [quantity, setQuantity] = useState(1);

  useEffect(() => {
    loadStocks();
  }, [minScore]);

  const loadStocks = async () => {
    const res = await fetchStocks(minScore);
    setStocks(res.data);
  };

  const handleRefresh = async () => {
    await refreshStocks();
    loadStocks();
  };

  const handleBuy = async (ticker) => {
    await buyStock(ticker, quantity);
    alert("Stock purchased");
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <button
          onClick={handleRefresh}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg"
        >
          Refresh Live Prices
        </button>

        <select
          value={minScore}
          onChange={(e) => setMinScore(e.target.value)}
          className="border p-2 rounded-lg"
        >
          <option value={0}>All Stocks</option>
          <option value={3}>Nyoro Score ≥ 3</option>
          <option value={4}>Nyoro Score ≥ 4</option>
          <option value={5}>Nyoro Score = 5</option>
        </select>
      </div>

      <table className="w-full bg-white shadow rounded-xl overflow-hidden">
        <thead className="bg-blue-800 text-white">
          <tr>
            <th className="p-3">Ticker</th>
            <th>Price</th>
            <th>P/E</th>
            <th>Dividend</th>
            <th>Nyoro Score</th>
            <th>Buy</th>
          </tr>
        </thead>
        <tbody>
          {stocks.map((stock) => (
            <tr key={stock.ticker} className="border-b text-center">
              <td className="p-3">{stock.ticker}</td>
              <td>${stock.price?.toFixed(2)}</td>
              <td>{stock.pe_ratio}</td>
              <td>{(stock.dividend_yield * 100).toFixed(2)}%</td>
              <td className="font-bold text-blue-700">
                {stock.nyoro_score}
              </td>
              <td>
                <input
                  type="number"
                  min="1"
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                  className="w-16 border rounded"
                />
                <button
                  onClick={() => handleBuy(stock.ticker)}
                  className="bg-green-500 text-white px-3 py-1 rounded ml-2"
                >
                  Buy
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default Watchlist;