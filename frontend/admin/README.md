# 管理前端（网页）

浏览器打开的运维后台（**不是 App**）。Vite + React + TypeScript。

## 页面

| 路由 | 说明 |
|------|------|
| `/login` | 登录 |
| `/resources` | 处理记录 |
| `/crawler` | 爬虫状态（无 TG） |
| `/parse-test` | 解析测试 |
| `/data` | 数据管理 |
| `/settings` | 账号 / 论坛 / 通用 |

当前列表等为**演示数据**；`vite` 将 `/api`、`/health`、`/parse` 代理到 Backend `:8080`。

## 启动

```powershell
cd e:\sehuatang\frontend\admin
npm install
npm run dev
```

访问：http://localhost:8081
