# TradeWise - 智慧投资追踪系统

## 项目概述
这是一个全栈个人投资追踪系统，帮助用户管理和分析股票、基金等投资资产，追踪投资收益并可视化展示投资组合表现。

## 技术栈

### 后端
- **框架**: Python 3 + FastAPI
- **数据库**: SQLite + SQLAlchemy ORM
- **数据源**: akshare (中国股票数据)
- **API端口**: 8001

### 前端
- **框架**: React 18 + Vite
- **样式**: TailwindCSS
- **图表库**: Recharts (收益曲线、饼图) + Lightweight Charts (K线图)
- **HTTP客户端**: Axios
- **开发端口**: 5173

## 核心功能

### 1. 数据同步
- 支持A股股票代码同步（如600519茅台、000333美的）
- 获取历史K线数据（开高低收、复权价格、成交量）
- 自动获取前复权、后复权数据

### 2. 交易记录管理
- CSV文件导入交易记录
- 自动去重机制
- 支持字段: date, symbol, type, quantity, price, fees
- 自动创建缺失的资产信息

### 3. 投资组合分析
- 总资产收益曲线（按时间序列计算）
- 持仓占比饼图
- 实时持仓详情表（持数量、当前价、市值、占比）

### 4. 个股分析
- K线图展示（支持前复权数据）
- 买卖点标记（红色买入箭头、绿色卖出箭头）
- 折线图模式切换
- 支持搜索和筛选股票

## 数据库设计

### Asset 表
- id: 主键
- symbol: 股票代码（唯一）
- name: 股票名称
- asset_type: 资产类型（stock/fund/future）

### Transaction 表
- id: 主键
- asset_id: 关联资产ID
- date: 交易日期
- type: 交易类型（buy/sell）
- quantity: 数量
- price: 价格
- fees: 手续费

### PriceHistory 表
- id: 主键
- asset_id: 关联资产ID
- date: 日期
- open, high, low, close: 原始价格
- adj_open, adj_high, adj_low, adj_close: 后复权价格
- qfq_open, qfq_high, qfq_low, qfq_close: 前复权价格
- volume: 成交量

## API端点

| 端点 | 方法 | 说明 |
|------|------|------|
| /assets | GET | 获取所有资产列表 |
| /assets/sync/{symbol} | POST | 同步指定股票数据 |
| /transactions/import | POST | 导入CSV交易记录 |
| /portfolio/summary | GET | 获取持仓汇总 |
| /portfolio/equity-curve | GET | 获取收益曲线 |
| /charts/{symbol} | GET | 获取图表数据 |
| /debug/transactions | GET | 调试：查看交易记录 |

## 项目结构

```
.
├── backend/           # 后端API服务
│   ├── main.py        # FastAPI主入口和路由
│   ├── models.py      # 数据库模型定义
│   ├── sync.py        # 数据同步逻辑（akshare）
│   ├── portfolio.py   # 投资组合计算逻辑
│   └── investments.db # SQLite数据库
├── frontend/          # 前端React应用
│   ├── src/
│   │   └── App.jsx    # 主应用组件
│   ├── package.json   # 前端依赖配置
│   ├── vite.config.js # Vite配置
│   └── tailwind.config.js # TailwindCSS配置
├── AI_PROMPT.md       # AI复现提示词
└── README.md          # 项目说明文档
```

## 快速启动

### 1. 安装后端依赖
```bash
cd backend
python -m pip install akshare fastapi uvicorn sqlalchemy pandas
```

### 2. 启动后端服务
```bash
cd backend
python main.py
```
后端API将运行在 `http://localhost:8001`

### 3. 安装前端依赖
```bash
cd frontend
npm install
```

### 4. 启动前端服务
```bash
cd frontend
npm run dev
```
前端应用将运行在 `http://localhost:5173` (或5174，取决于端口占用情况)

## 使用流程

1. **同步数据**
   - 在顶部栏输入股票代码或从下拉列表选择
   - 点击"同步数据"按钮获取历史价格数据

2. **导入交易记录**
   - 准备CSV文件，格式：date, symbol, type, quantity, price, fees
   - 进入Transactions页面，上传CSV文件

3. **查看投资组合**
   - Dashboard页面显示收益曲线、持仓占比、持仓详情

4. **个股分析**
   - 进入Analysis页面
   - 搜索或选择股票
   - 查看K线图和买卖点标记

## CSV导入格式示例

```csv
date,symbol,type,quantity,price,fees
2024-01-02,600519,buy,100,1650.0,0
2024-01-15,600519,buy,50,1600.0,0
2024-06-01,600519,sell,100,1800.0,0
```

## 技术特性

- **自动去重**: 导入交易记录时自动跳过重复数据
- **前复权数据**: 使用前复权价格进行K线展示和收益计算
- **响应式设计**: 前端适配不同屏幕尺寸
- **实时更新**: 数据变化后自动刷新页面
- **错误处理**: 完善的异常捕获和用户提示

## 扩展建议

- 添加用户认证和权限管理
- 支持多种数据源（如雅虎财经、Alpha Vantage）
- 添加更多技术指标（MACD、RSI、KDJ等）
- 实现数据导出功能
- 添加邮件/短信预警功能
- 支持国际市场（美股、港股等）
