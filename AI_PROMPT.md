# AI 提示词 - 复现 TradeWise 智慧投资追踪系统

```
请帮我创建一个全栈个人投资追踪系统，包含以下功能：

## 技术栈要求
- 后端：Python + FastAPI + SQLite + SQLAlchemy
- 前端：React 18 + Vite + TailwindCSS
- 数据源：akshare（中国股票数据）
- 图表库：Recharts（收益曲线、饼图）+ Lightweight Charts（K线图）

## 后端功能
1. 数据模型设计
   - Asset表：存储资产信息（代码、名称、类型）
   - Transaction表：存储交易记录（日期、类型、数量、价格、手续费）
   - PriceHistory表：存储历史价格数据（开高低收、前复权、后复权、成交量）

2. API端点
   - GET /assets：获取所有资产列表
   - POST /assets/sync/{symbol}：使用akshare同步股票历史数据
   - POST /transactions/import：导入CSV交易记录，支持自动去重
   - GET /portfolio/summary：计算当前持仓（持数量、当前价、市值、占比）
   - GET /portfolio/equity-curve：计算总资产收益曲线
   - GET /charts/{symbol}：获取K线数据和买卖点标记

3. 核心逻辑
   - 使用akshare获取A股历史数据（支持前复权、后复权）
   - 计算持仓：买入加数量，卖出减数量，过滤掉已平仓
   - 计算收益曲线：按时间序列遍历，计算每日总资产值

## 前端功能
1. 页面布局
   - 侧边栏导航：Dashboard、Transactions、Analysis
   - 顶部栏：数据同步输入框、总资产显示

2. Dashboard页面
   - 收益曲线图（Recharts LineChart）
   - 持仓占比饼图（Recharts PieChart）
   - 实时持仓详情表格

3. Transactions页面
   - CSV文件上传功能
   - 导入成功后自动刷新数据

4. Analysis页面
   - 股票搜索和下拉选择
   - K线图（Lightweight Charts）
   - 折线图模式切换
   - 买卖点标记（红色箭头买入，绿色箭头卖出）
   - 支持K线和折线双模式显示

## 技术细节
- 使用Axios进行API请求
- 使用React Hooks管理状态
- 后端启用CORS支持
- 处理浮点数特殊值（inf、nan）
- 图表支持响应式布局

## 启动方式
后端：cd backend && python main.py（运行在8001端口）
前端：cd frontend && npm run dev（运行在5173端口）

请按照以上要求创建完整的项目代码，包括所有必要的配置文件、依赖管理和启动脚本。
```

## 数据库设计详细说明

### models.py - 数据模型

```python
from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy import create_engine

Base = declarative_base()

class Asset(Base):
    __tablename__ = 'assets'
    id = Column(Integer, primary_key=True)
    symbol = Column(String, unique=True, nullable=False)  # 股票代码
    name = Column(String)  # 股票名称
    asset_type = Column(String)  # 'stock', 'fund', 'future'
    
    prices = relationship("PriceHistory", back_populates="asset", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="asset")

class PriceHistory(Base):
    __tablename__ = 'price_history'
    id = Column(Integer, primary_key=True)
    asset_id = Column(Integer, ForeignKey('assets.id'), nullable=False)
    date = Column(Date, nullable=False)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    # 后复权数据 (hfq)
    adj_open = Column(Float)
    adj_high = Column(Float)
    adj_low = Column(Float)
    adj_close = Column(Float)
    # 前复权数据 (qfq)
    qfq_open = Column(Float)
    qfq_high = Column(Float)
    qfq_low = Column(Float)
    qfq_close = Column(Float)
    volume = Column(Float)

    asset = relationship("Asset", back_populates="prices")
    __table_args__ = (UniqueConstraint('asset_id', 'date', name='_asset_date_uc'),)

class Transaction(Base):
    __tablename__ = 'transactions'
    id = Column(Integer, primary_key=True)
    asset_id = Column(Integer, ForeignKey('assets.id'), nullable=False)
    date = Column(Date, nullable=False)
    type = Column(String)  # 'buy', 'sell'
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    fees = Column(Float, default=0.0)
    
    asset = relationship("Asset", back_populates="transactions")
```

## API 实现关键点

### 1. 数据同步 (sync.py)

```python
import akshare as ak
from models import SessionLocal, Asset, PriceHistory
from sqlalchemy.exc import IntegrityError

def sync_asset_data(symbol, asset_type="stock"):
    """使用akshare同步股票历史数据"""
    db = SessionLocal()
    
    try:
        # 获取股票信息
        stock_info = ak.stock_info_a_code_name()
        stock_row = stock_info[stock_info['code'] == symbol]
        name = stock_row['name'].values[0] if len(stock_row) > 0 else None
        
        # 创建或获取资产
        asset = db.query(Asset).filter(Asset.symbol == symbol).first()
        if not asset:
            asset = Asset(symbol=symbol, name=name, asset_type=asset_type)
            db.add(asset)
            db.commit()
            db.refresh(asset)
        
        # 获取历史K线数据（前复权）
        df = ak.stock_zh_a_hist(symbol=symbol, period="daily", 
                               start_date="19900101", adjust="qfq")
        
        # 获取后复权数据
        df_adj = ak.stock_zh_a_hist(symbol=symbol, period="daily", 
                                   start_date="19900101", adjust="hfq")
        
        # 插入价格数据
        for _, row in df.iterrows():
            adj_row = df_adj[df_adj['日期'] == row['日期']]
            
            price = PriceHistory(
                asset_id=asset.id,
                date=pd.to_datetime(row['日期']).date(),
                open=row['开盘'],
                high=row['最高'],
                low=row['最低'],
                close=row['收盘'],
                volume=row['成交量'],
                # 后复权数据
                adj_open=adj_row['开盘'].values[0] if len(adj_row) > 0 else None,
                adj_high=adj_row['最高'].values[0] if len(adj_row) > 0 else None,
                adj_low=adj_row['最低'].values[0] if len(adj_row) > 0 else None,
                adj_close=adj_row['收盘'].values[0] if len(adj_row) > 0 else None,
                # 前复权数据（当前行）
                qfq_open=row['开盘'],
                qfq_high=row['最高'],
                qfq_low=row['最低'],
                qfq_close=row['收盘']
            )
            
            try:
                db.add(price)
                db.commit()
            except IntegrityError:
                db.rollback()  # 跳过重复日期
                
    finally:
        db.close()
```

### 2. 投资组合计算 (portfolio.py)

```python
from sqlalchemy.orm import Session
from models import Transaction, PriceHistory, Asset
from datetime import date
from collections import defaultdict

def calculate_portfolio_holdings(db: Session):
    """计算当前持仓"""
    txs = db.query(Transaction).all()
    holdings = defaultdict(float)
    
    for tx in txs:
        asset = tx.asset
        if tx.type == 'buy':
            holdings[asset.symbol] += tx.quantity
        elif tx.type == 'sell':
            holdings[asset.symbol] -= tx.quantity
    
    # 过滤掉已平仓的持仓
    return {s: q for s, q in holdings.items() if q > 0}

def get_portfolio_allocation(db: Session):
    """计算持仓分布"""
    holdings = calculate_portfolio_holdings(db)
    
    if not holdings:
        return {"items": [], "total_value": 0}
    
    allocation = []
    total_value = 0
    
    for symbol, quantity in holdings.items():
        asset = db.query(Asset).filter(Asset.symbol == symbol).first()
        if not asset or not asset.name:
            continue
            
        # 获取最新价格
        latest_price = db.query(PriceHistory).filter(
            PriceHistory.asset_id == asset.id
        ).order_by(PriceHistory.date.desc()).first()
        
        price = latest_price.close if latest_price else 0
        value = quantity * price
        total_value += value
        
        allocation.append({
            "symbol": symbol,
            "name": asset.name,
            "quantity": quantity,
            "price": price,
            "value": value
        })
    
    # 计算百分比
    for item in allocation:
        item["percentage"] = (item["value"] / total_value * 100) if total_value > 0 else 0
        
    return {"items": allocation, "total_value": total_value}

def calculate_equity_curve(db: Session):
    """计算收益曲线"""
    txs = db.query(Transaction).order_by(Transaction.date).all()
    if not txs:
        return []
    
    start_date = txs[0].date
    end_date = date.today()
    
    # 获取所有价格日期
    price_dates = db.query(PriceHistory.date).distinct().filter(
        PriceHistory.date >= start_date
    ).order_by(PriceHistory.date).all()
    
    all_dates = [d[0] for d in price_dates]
    equity_curve = []
    current_holdings = defaultdict(float)
    tx_idx = 0
    
    for d in all_dates:
        # 更新持仓
        while tx_idx < len(txs) and txs[tx_idx].date <= d:
            t = txs[tx_idx]
            asset_symbol = t.asset.symbol
            if t.type == 'buy':
                current_holdings[asset_symbol] += t.quantity
            else:
                current_holdings[asset_symbol] -= t.quantity
            tx_idx += 1
            
        # 计算每日价值
        daily_value = 0
        for symbol, qty in current_holdings.items():
            if qty == 0: continue
            asset = db.query(Asset).filter(Asset.symbol == symbol).first()
            p = db.query(PriceHistory).filter(
                PriceHistory.asset_id == asset.id,
                PriceHistory.date == d
            ).first()
            
            if p:
                daily_value += qty * p.close
            else:
                # 找最近的价格
                p_last = db.query(PriceHistory).filter(
                    PriceHistory.asset_id == asset.id,
                    PriceHistory.date < d
                ).order_by(PriceHistory.date.desc()).first()
                if p_last:
                    daily_value += qty * p_last.close
                    
        equity_curve.append({"time": str(d), "value": daily_value})
        
    return equity_curve
```

## 前端组件结构

### App.jsx 主要组件

```jsx
// 1. AssetChart - K线图组件
function AssetChart({ symbol, resetKey, chartMode }) {
    // 使用lightweight-charts创建K线图
    // 支持candlestick和line两种模式
    // 显示买卖点标记
}

// 2. Dashboard - 仪表盘页面
// - 收益曲线（LineChart）
// - 持仓占比（PieChart）
// - 持仓详情表格

// 3. Transactions - 交易记录页面
// - CSV文件上传
// - 调用 /transactions/import API

// 4. Analysis - 个股分析页面
// - 股票搜索和选择
// - K线图/折线图切换
// - 显示买卖点标记
```

## 项目依赖

### backend/requirements.txt
```
fastapi==0.104.1
uvicorn==0.24.0
sqlalchemy==2.0.23
akshare==1.12.58
pandas==2.1.3
```

### frontend/package.json
```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "recharts": "^2.10.3",
    "lightweight-charts": "^4.1.1",
    "axios": "^1.6.2",
    "lucide-react": "^0.294.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.2.0",
    "vite": "^5.0.0",
    "tailwindcss": "^3.3.5"
  }
}
```

## CSV 导入格式示例

```csv
date,symbol,type,quantity,price,fees
2024-01-02,600519,buy,100,1650.0,0
2024-01-15,600519,buy,50,1600.0,0
2024-06-01,600519,sell,100,1800.0,0
```

## 实现顺序建议

1. **第一步**: 创建数据库模型（models.py）
2. **第二步**: 实现数据同步功能（sync.py）
3. **第三步**: 创建API端点（main.py）
4. **第四步**: 实现投资组合计算逻辑（portfolio.py）
5. **第五步**: 创建前端基础结构
6. **第六步**: 实现Dashboard页面
7. **第七步**: 实现Transactions页面
8. **第八步**: 实现Analysis页面和图表

## 常见问题解决

1. **akshare数据获取失败**: 检查网络连接，确保股票代码格式正确
2. **图表不显示**: 检查数据格式，确保时间戳格式正确
3. **前端无法访问后端**: 确保CORS已正确配置
4. **数据库锁定**: 关闭所有数据库连接，删除锁文件

## 扩展功能建议

- 用户认证和权限管理
- 多种数据源支持（雅虎财经、Alpha Vantage）
- 技术指标分析（MACD、RSI、KDJ）
- 数据导出功能（Excel、PDF）
- 邮件/短信预警
- 国际市场支持（美股、港股）
- 移动端适配
- 实时WebSocket数据推送
