import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { createChart } from 'lightweight-charts';
import { PieChart, Pie, Cell, ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, Legend } from 'recharts';
import { LayoutDashboard, Receipt, LineChart as ChartIcon, PieChart as PieIcon, Upload, RefreshCw } from 'lucide-react';

const API_BASE = "http://localhost:8001";

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8'];

function AssetChart({ symbol, resetKey, chartMode }) {
    const chartContainerRef = React.useRef();
    const chartRef = React.useRef();
    const abortControllerRef = React.useRef();
    const resizeObserverRef = React.useRef();

    useEffect(() => {
        if (!symbol) return;

        abortControllerRef.current = new AbortController();

        const fetchChartData = async () => {
            try {
                if (abortControllerRef.current.signal.aborted) return;

                if (chartRef.current) {
                    chartRef.current.remove();
                    chartRef.current = null;
                }

                const res = await axios.get(`${API_BASE}/charts/${symbol}`, {
                    signal: abortControllerRef.current.signal
                });

                if (abortControllerRef.current.signal.aborted) return;

                const { prices, markers } = res.data;

                if (!chartContainerRef.current) return;

                const chart = createChart(chartContainerRef.current, {
                    layout: { background: { color: '#ffffff' }, textColor: '#374151' },
                    grid: { vertLines: { color: '#e5e7eb' }, horzLines: { color: '#e5e7eb' } },
                    width: chartContainerRef.current.clientWidth,
                    height: chartContainerRef.current.clientHeight,
                });

                // 根据模式显示不同的图表
                if (chartMode === 'candlestick' || chartMode === 'both') {
                    // 创建K线系列
                    const candleSeries = chart.addCandlestickSeries({
                        title: 'K线图'
                    });
                    const adjustedPrices = prices.map(p => ({
                        time: p.time,
                        open: p.qfq_open,
                        high: p.qfq_high,
                        low: p.qfq_low,
                        close: p.qfq_close
                    }));
                    candleSeries.setData(adjustedPrices);
                    if (chartMode === 'candlestick' && markers) {
                        candleSeries.setMarkers(markers);
                    }
                }

                if (chartMode === 'line' || chartMode === 'both') {
                    // 创建平滑折线系列（收盘价）
                    const lineSeries = chart.addLineSeries({
                        title: '收盘价',
                        color: '#6366f1',
                        lineWidth: 2,
                        priceLineVisible: false,
                        lastValueVisible: true,
                    });
                    
                    const lineData = prices.map(p => ({
                        time: p.time,
                        value: p.qfq_close
                    }));
                    lineSeries.setData(lineData);

                    // 添加交易点标记（红点买入，绿点卖出）- 使用圆点显示在线图上
                    if (markers && markers.length > 0) {
                        const tradeMarkers = markers.map(m => ({
                            time: m.time,
                            position: 'inBar', // 显示在折线上
                            color: m.color === 'red' ? '#ef4444' : '#22c55e', // 红点买入，绿点卖出
                            shape: 'circle', // 圆点形状
                            text: m.text,
                            size: 1.5 // 圆点大小（较小）
                        }));
                        lineSeries.setMarkers(tradeMarkers);
                    }
                }

                chartRef.current = chart;

                // 默认显示最近1年的数据（约250个交易日）
                const totalBars = adjustedPrices.length;
                const barsToShow = Math.min(250, totalBars); // 250个交易日 ≈ 1年
                if (totalBars > barsToShow) {
                    chart.timeScale().setVisibleLogicalRange({
                        from: totalBars - barsToShow,
                        to: totalBars - 1
                    });
                } else {
                    chart.timeScale().fitContent();
                }

                // 监听容器尺寸变化，自动调整图表大小
                resizeObserverRef.current = new ResizeObserver((entries) => {
                    if (chartRef.current && entries[0]) {
                        const { width, height } = entries[0].contentRect;
                        chartRef.current.applyOptions({ width, height });
                    }
                });

                if (chartContainerRef.current) {
                    resizeObserverRef.current.observe(chartContainerRef.current);
                }
            } catch (err) {
                if (!axios.isCancel(err)) {
                    console.error("Failed to fetch chart data", err);
                }
            }
        };

        fetchChartData();

        return () => {
            if (abortControllerRef.current) {
                abortControllerRef.current.abort();
            }
            if (resizeObserverRef.current) {
                resizeObserverRef.current.disconnect();
            }
            if (chartRef.current) {
                chartRef.current.remove();
                chartRef.current = null;
            }
        };
    }, [symbol, resetKey, chartMode]);

    return <div ref={chartContainerRef} className="w-full h-[600px]" />;
}

export default function App() {
    const [activeTab, setActiveTab] = useState('dashboard');
    const [资产, set资产] = useState([]);
    const [portfolioSummary, setPortfolioSummary] = useState({ items: [], total_value: 0 });
    const [equityCurve, setEquityCurve] = useState([]);
    const [syncSymbol, setSyncSymbol] = useState('');
    const [selectedAnalysisSymbol, setSelectedAnalysisSymbol] = useState('');
    const [analysisSearchQuery, setAnalysisSearchQuery] = useState('');
    const [chartResetKey, setChartResetKey] = useState(0);
    const [loading, setLoading] = useState(false);
    const [chartMode, setChartMode] = useState('candlestick');
    const [analysisViewMode, setAnalysisViewMode] = useState('all'); // 'all' or 'traded'
    const [tradedAssets, setTradedAssets] = useState([]);

    // 过滤分析页面的股票列表
    const filteredAnalysisAssets = (analysisViewMode === 'traded' ? tradedAssets : 资产).filter(item => {
        if (!analysisSearchQuery) return true;
        const query = analysisSearchQuery.toLowerCase();
        return item.symbol.toLowerCase().includes(query) ||
               (item.name && item.name.toLowerCase().includes(query));
    });

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        try {
            const assetsRes = await axios.get(`${API_BASE}/assets`);
            set资产(assetsRes.data);

            // Fetch assets with transactions
            const tradedRes = await axios.get(`${API_BASE}/assets/with-transactions`);
            setTradedAssets(tradedRes.data);

            const summaryRes = await axios.get(`${API_BASE}/portfolio/summary`);
            setPortfolioSummary(summaryRes.data);

            const curveRes = await axios.get(`${API_BASE}/portfolio/equity-curve`);
            setEquityCurve(curveRes.data);
        } catch (err) {
            console.error("Failed to fetch data", err);
        }
    };

    const handleSync = async () => {
        if (!syncSymbol) return;
        setLoading(true);
        try {
            await axios.post(`${API_BASE}/assets/sync/${syncSymbol}`);
            fetchData();
            setSyncSymbol('');
        } catch (err) {
            alert("同步失败");
        }
        setLoading(false);
    };

    return (
        <div className="min-h-screen bg-gray-50 text-gray-900 flex font-sans">
            {/* Sidebar */}
            <div className="w-64 bg-white border-r border-gray-200 flex flex-col p-4 shadow-sm">
                <h1 className="text-xl font-bold mb-8 flex items-center gap-2 text-indigo-600">
                    <LayoutDashboard size={24} />
                    TradeWise 智投
                </h1>
                <nav className="flex-1 space-y-2">
                    {['dashboard', 'transactions', 'analysis'].map(tab => (
                        <button
                            key={tab}
                            onClick={() => setActiveTab(tab)}
                            className={`w-full text-left px-4 py-2 rounded-lg flex items-center gap-3 transition-colors text-gray-700 ${activeTab === tab ? 'bg-indigo-100 text-indigo-700 border border-indigo-200' : 'hover:bg-gray-100'
                                }`}
                        >
                            {tab === 'dashboard' && <ChartIcon size={18} />}
                            {tab === 'transactions' && <Receipt size={18} />}
                            {tab === 'analysis' && <PieIcon size={18} />}
                            {tab.charAt(0).toUpperCase() + tab.slice(1)}
                        </button>
                    ))}
                </nav>
            </div>

            {/* Main Content */}
            <div className="flex-1 flex flex-col overflow-hidden">
                <header className="h-16 bg-white border-b border-gray-200 flex items-center px-8 justify-between shadow-sm">
                    <div className="flex items-center gap-4">
                        <select
                            value={syncSymbol}
                            onChange={e => setSyncSymbol(e.target.value)}
                            className="bg-white border border-gray-300 px-3 py-1 rounded text-sm focus:outline-none focus:ring-2 ring-indigo-500 text-gray-700"
                        >
                            <option value="">选择或输入标的代码</option>
                            {资产.filter(a => a.name && a.name.trim() !== '').map(a => (
                                <option key={a.symbol} value={a.symbol}>{a.symbol} ({a.name})</option>
                            ))}
                        </select>
                        <input
                            value={syncSymbol}
                            onChange={e => setSyncSymbol(e.target.value)}
                            placeholder="或输入代码 (如 600519)"
                            className="bg-gray-100 border border-gray-300 px-3 py-1 rounded text-sm focus:outline-none focus:ring-2 ring-indigo-500 w-48"
                        />
                        <button
                            onClick={handleSync}
                            disabled={loading}
                            className="bg-white border border-indigo-500 text-indigo-600 hover:bg-indigo-50 px-4 py-1.5 rounded text-sm font-medium flex items-center gap-2 transition-colors"
                        >
                            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
                            同步数据
                        </button>
                    </div>
                    <div className="text-sm">
                        总资产: <span className="text-emerald-600 font-bold text-lg">¥{portfolioSummary.total_value.toLocaleString()}</span>
                    </div>
                </header>

                <main className="flex-1 overflow-y-auto p-8">
                    {activeTab === 'dashboard' && (
                        <div className="space-y-8">
                            {/* Equity Curve */}
                            <div className="bg-white p-6 rounded-xl border border-gray-200">
                                <h2 className="text-lg font-semibold mb-4 text-gray-700">收益曲线 (总资产值)</h2>
                                <div className="h-64">
                                    <ResponsiveContainer width="100%" height="100%">
                                        <LineChart data={equityCurve}>
                                            <XAxis dataKey="time" stroke="#6b7280" fontSize={12} />
                                            <YAxis stroke="#6b7280" fontSize={12} />
                                            <Tooltip
                                                contentStyle={{ backgroundColor: '#ffffff', border: '1px solid #e5e7eb', borderRadius: '8px' }}
                                                itemStyle={{ color: '#4f46e5' }}
                                            />
                                            <Line type="monotone" dataKey="value" stroke="#6366f1" strokeWidth={2} dot={false} />
                                        </LineChart>
                                    </ResponsiveContainer>
                                </div>
                            </div>

                            {/* Asset Grid */}
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                                <div className="bg-white p-6 rounded-xl border border-gray-200">
                                    <h2 className="text-lg font-semibold mb-4 text-gray-700">持仓占比</h2>
                                    <div className="h-64">
                                        <ResponsiveContainer width="100%" height="100%">
                                            <PieChart>
                                                <Pie
                                                    data={portfolioSummary.items}
                                                    cx="50%"
                                                    cy="50%"
                                                    innerRadius={60}
                                                    outerRadius={80}
                                                    paddingAngle={5}
                                                    dataKey="value"
                                                    nameKey="symbol"
                                                >
                                                    {portfolioSummary.items.map((entry, index) => (
                                                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                                    ))}
                                                </Pie>
                                                <Tooltip contentStyle={{ backgroundColor: '#ffffff', border: '1px solid #e5e7eb' }} />
                                                <Legend />
                                            </PieChart>
                                        </ResponsiveContainer>
                                    </div>
                                </div>

                                <div className="bg-white p-6 rounded-xl border border-gray-200">
                                    <h2 className="text-lg font-semibold mb-4 text-gray-700">实时持仓详情</h2>
                                    <div className="overflow-x-auto">
                                        <table className="w-full text-left text-sm">
                                            <thead>
                                                <tr className="border-b border-gray-200 text-text-gray-500">
                                                    <th className="pb-2">代码/名称</th>
                                                    <th className="pb-2">持数量</th>
                                                    <th className="pb-2">当前价</th>
                                                    <th className="pb-2">市值</th>
                                                    <th className="pb-2">占比</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {portfolioSummary.items.map((item, idx) => (
                                                    <tr key={idx} className="border-b border-gray-200/50 hover:bg-gray-100/30">
                                                        <td className="py-3">
                                                            <div className="font-medium">{item.symbol}</div>
                                                            <div className="text-xs text-gray-500">{item.name || '未知'}</div>
                                                        </td>
                                                        <td>{item.quantity}</td>
                                                        <td>¥{item.price.toFixed(2)}</td>
                                                        <td className="text-emerald-400">¥{item.value.toLocaleString()}</td>
                                                        <td>{item.percentage.toFixed(1)}%</td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {activeTab === 'analysis' && (
                        <div className="space-y-8">
                            <div className="bg-white p-6 rounded-xl border border-gray-200">
                                <h2 className="text-lg font-semibold mb-4 text-gray-700">个股分析 - 选择标的</h2>

                                {/* 视图模式切换 */}
                                <div className="flex gap-2 mb-4">
                                    <button
                                        onClick={() => setAnalysisViewMode('all')}
                                        className={`px-3 py-1.5 text-xs rounded border transition-colors ${
                                            analysisViewMode === 'all'
                                                ? 'bg-indigo-600 text-white border-indigo-600'
                                                : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
                                        }`}
                                    >
                                        所有标的 ({资产.length})
                                    </button>
                                    <button
                                        onClick={() => setAnalysisViewMode('traded')}
                                        className={`px-3 py-1.5 text-xs rounded border transition-colors ${
                                            analysisViewMode === 'traded'
                                                ? 'bg-indigo-600 text-white border-indigo-600'
                                                : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
                                        }`}
                                    >
                                        持仓历史 ({tradedAssets.length})
                                    </button>
                                </div>

                                {/* 搜索和下拉选择 */}
                                <div className="flex flex-col sm:flex-row gap-4 mb-6">
                                    <div className="relative flex-1">
                                        <input
                                            type="text"
                                            placeholder="搜索股票代码或名称..."
                                            value={analysisSearchQuery}
                                            onChange={(e) => setAnalysisSearchQuery(e.target.value)}
                                            className="w-full bg-gray-100 border border-gray-300 px-4 py-2 rounded-lg focus:outline-none focus:ring-2 ring-indigo-500 text-sm"
                                        />
                                        {analysisSearchQuery && (
                                            <button
                                                onClick={() => setAnalysisSearchQuery('')}
                                                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                                            >
                                                ✕
                                            </button>
                                        )}
                                    </div>
                                    <select
                                        value={selectedAnalysisSymbol}
                                        onChange={(e) => setSelectedAnalysisSymbol(e.target.value)}
                                        className="bg-gray-100 border border-gray-300 px-4 py-2 rounded-lg focus:outline-none focus:ring-2 ring-indigo-500 text-sm min-w-[200px]"
                                    >
                                        <option value="">选择标的</option>
                                        {filteredAnalysisAssets.filter(item => item.name && item.name.trim() !== '').map(item => (
                                            <option key={item.symbol} value={item.symbol}>
                                                {item.symbol} ({item.name})
                                            </option>
                                        ))}
                                    </select>
                                </div>

                                {/* 显示当前选中的标的 */}
                                {selectedAnalysisSymbol && (
                                    <div className="mb-4 p-3 bg-gray-100 rounded-lg flex items-center justify-between">
                                        <div>
                                            <span className="text-lg font-bold text-indigo-600">{selectedAnalysisSymbol}</span>
                                            <span className="text-gray-500 ml-2">
                                                {资产.find(a => a.symbol === selectedAnalysisSymbol)?.name || '未知'}
                                            </span>
                                        </div>
                                        <button
                                            onClick={() => setSelectedAnalysisSymbol('')}
                                            className="text-gray-500 hover:text-gray-700 text-sm px-3 py-1 rounded bg-gray-100 hover:bg-gray-200 transition-colors"
                                        >
                                            清除选择
                                        </button>
                                    </div>
                                )}

                                {selectedAnalysisSymbol && (
                                    <div className="mb-4 flex justify-end">
                                        <button
                                            onClick={() => setChartResetKey(prev => prev + 1)}
                                            className="text-xs px-3 py-1.5 rounded border border-gray-300 text-gray-600 hover:bg-gray-100 transition-colors whitespace-nowrap"
                                        >
                                            重置视图
                                        </button>
                                    </div>
                                )}

                                    <div className="flex items-center gap-2 mb-4">
                                        <span className="text-sm text-gray-600">图表模式:</span>
                                        <div className="flex gap-1">
                                             {[
                                                { key: 'candlestick', label: 'K线' },
                                                { key: 'line', label: '折线' }
                                            ].map(({ key, label }) => (
                                                <button
                                                    key={key}
                                                    onClick={() => setChartMode(key)}
                                                    className={`px-3 py-1.5 text-xs rounded border transition-colors ${
                                                        chartMode === key
                                                            ? 'bg-indigo-600 text-white border-indigo-600'
                                                            : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
                                                    }`}
                                                >
                                                    {label}
                                                </button>
                                            ))}
                                        </div>
                                    </div>

                                {selectedAnalysisSymbol ? (
                                    <div className="mx-auto">
                                        <AssetChart symbol={selectedAnalysisSymbol} resetKey={chartResetKey} chartMode={chartMode} />
                                    </div>
                                ) : (
                                    <div className="h-64 flex items-center justify-center text-gray-500">
                                        {filteredAnalysisAssets.length === 0 && analysisSearchQuery ? (
                                            <>未找到匹配的股票</>
                                        ) : (
                                            <>搜索或从下拉列表选择一个标的查看 K 线及买卖点</>
                                        )}
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {activeTab === 'transactions' && (
                        <div className="bg-white p-6 rounded-xl border border-gray-200 max-w-2xl mx-auto text-center">
                            <div className="mb-6 inline-block p-4 rounded-full bg-gray-100 text-indigo-600">
                                <Upload size={48} />
                            </div>
                            <h2 className="text-xl font-bold mb-2">导入投资记录</h2>
                            <p className="text-gray-500 mb-8">上传 CSV 文件。格式要求: date, symbol, type, quantity, price, fees</p>
                            <input type="file" className="hidden" id="csv-upload" onChange={async (e) => {
                                const file = e.target.files[0];
                                if (!file) return;
                                const formData = new FormData();
                                formData.append('file', file);
                                try {
                                    await axios.post(`${API_BASE}/transactions/import`, formData);
                                    alert("导入成功");
                                    fetchData();
                                } catch (err) { alert("导入失败"); }
                            }} />
                            <label htmlFor="csv-upload" className="bg-white border-2 border-indigo-500 text-indigo-600 hover:bg-indigo-50 px-8 py-3 rounded-lg cursor-pointer font-bold inline-block transition-colors">
                                选择文件并上传
                            </label>
                        </div>
                    )}
                </main>
            </div>
        </div>
    );
}
