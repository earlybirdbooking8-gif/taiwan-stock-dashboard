# Project Rules

## CI/CD 自動化發布流程 (Deployment Pipeline)
完成每項功能後，必須依照以下 6 個步驟自動執行：

【第一步：執行測試】
- 執行所有本地測試。
- 若測試失敗：修正錯誤 -> 重新測試 -> 測試全部通過才能繼續。

【第二步：同步 GitHub】
- `git add .`
- 撰寫有意義的 Commit Message (遵循下方規範)
- `git commit`
- `git push origin main`

【第三步：驗證部署 (Streamlit Community Cloud)】
- 由於專案已綁定 Streamlit Community Cloud，只要 GitHub Push 成功，遠端伺服器將會自動拉取最新程式碼並重啟部署。
- 開啟 Streamlit 應用程式專屬網址，確認新功能已成功上線且運作正常。

- **核心原則**：GitHub Repository 為唯一正式版本（Single Source of Truth）。未測試成功不得 Push。專案採用 GitOps 流程，任何修改推播至 GitHub main 分支後，即視為完成自動化發布。

## Commit Message 規範
遵循 Conventional Commits 規範：
- `feat:` 新增功能 (例如: feat: 新增夜盤資料分析)
- `fix:` 修正錯誤 (例如: fix: 修正 PDF 無法下載)
- `refactor:` 重構程式碼 (例如: refactor: 重構資料同步模組)
- `style:` 程式碼格式調整
- `docs:` 說明文件更新
- `test:` 測試相關
- `chore:` 雜項、建置工具等更新

## Branching 規範
任何重大修改請先建立新 Branch，經確認後再合併到 main：
- `feature/*`
- `bugfix/*`
- `hotfix/*`
