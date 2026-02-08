# 项目启动指南 (TradeWise - 智慧投资追踪系统)

## 技术栈

- **后端**: Python 3 + FastAPI (SQLite, akshare) - 端口 8001
- **前端**: React 18 + Vite + TailwindCSS - 端口 5173

## 快速启动

```bash
# 终端1 - 启动后端 (必须使用 python3)
cd /home/zhangguangwei/workspace/INV/backend
python3 main.py

# 终端2 - 启动前端
cd /home/zhangguangwei/workspace/INV/frontend
npm run dev
```

## 验证启动

- 前端: http://localhost:5173
- 后端API: http://localhost:8001

## 依赖安装

```bash
# 后端依赖
cd /home/zhangguangwei/workspace/INV/backend
python3 -m pip install akshare fastapi uvicorn sqlalchemy pandas

# 前端依赖
cd /home/zhangguangwei/workspace/INV/frontend
npm install
```

## 关键启动命令

| 服务 | 命令 |
|------|------|
| 后端 | `cd /home/zhangguangwei/workspace/INV/backend && python3 main.py` |
| 前端 | `cd /home/zhangguangwei/workspace/INV/frontend && npm run dev` |

**注意**: 后端必须使用 `python3` 命令，而非 `python`。
