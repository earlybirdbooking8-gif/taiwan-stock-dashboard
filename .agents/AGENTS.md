# Project Rules

## Git Workflow & Development Rules
- 每完成一項功能，必須執行以下流程：
  1. 執行測試
  2. 修正所有錯誤
  3. `git add .`
  4. 撰寫有意義的 Commit Message
  5. `git commit`
  6. `git push origin main`
- 未測試成功不得 Push。
- 任何程式修改都必須先修改本地專案，通過測試，自動 Commit 並 Push 到 GitHub。
- GitHub Repository 為唯一正式版本（Single Source of Truth）。

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
