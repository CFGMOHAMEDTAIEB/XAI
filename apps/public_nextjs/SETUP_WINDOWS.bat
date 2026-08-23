@echo off
where node >nul 2>nul || (echo ERROR: Node.js is missing. & exit /b 1)
if not exist .env.local copy .env.example .env.local
npm install
if errorlevel 1 exit /b 1
npm run typecheck
if errorlevel 1 exit /b 1
npm run build
if errorlevel 1 exit /b 1
echo Public Next.js website is ready. Run: npm run dev
