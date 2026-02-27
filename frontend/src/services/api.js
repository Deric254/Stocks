import axios from "axios";

const API = axios.create({
  baseURL: "http://localhost:8000"
});

export const fetchStocks = (minScore = 0) =>
  API.get(`/stocks?min_score=${minScore}`);

export const refreshStocks = () =>
  API.get(`/stocks/refresh`);

export const buyStock = (ticker, quantity) =>
  API.post(`/portfolio/buy?ticker=${ticker}&quantity=${quantity}`);

export const sellStock = (id) =>
  API.post(`/portfolio/sell?portfolio_id=${id}`);

export const getPortfolio = () =>
  API.get(`/portfolio`);

export const getSummary = () =>
  API.get(`/analytics/summary`);

export const getPositions = () =>
  API.get(`/analytics/positions`);