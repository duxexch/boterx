# VEX Deals - AI Agent Master Prompt & Execution Guide

If you are an AI coding agent or developer taking over or running this project, read this file to understand the architecture, commands, and operational workflow.

## 🚀 Quick Start Prompt for AI Agents
> "You are managing the VEX Deals Loyalty, Compensation, and AI Sports Forecasting Platform. This project is a full-stack Node.js + Express + TypeScript + Vite React application featuring real-time Socket.io communication, Gemini AI tactical match analysis, Firebase Firestore/Auth, Firebase Cloud Messaging (FCM), and a built-in Docker background notification worker (`server.ts`). 
> Your goal is to ensure the app builds cleanly via `npm run build`, starts successfully via `npm start`, and responds correctly on port 3000."

---

## 🛠️ Project Architecture & Stack
- **Frontend**: React 18+, Vite, Tailwind CSS, Lucide React, Recharts, Motion.
- **Backend**: Node.js, Express, TypeScript, Socket.io (with auto-reconnection and heartbeat).
- **Database & Storage**: Firebase Firestore & Auth (`firebase-applet-config.json`).
- **Push Notifications**: Firebase Cloud Messaging (FCM) + Fallback Docker Background Notification Worker.
- **AI Engine**: Google Gemini API (`@google/genai` v2.4.0) for match tactical analysis and predictions.

---

## 💻 Essential Terminal Commands
1. **Install Dependencies**:
   ```bash
   npm install
   ```
2. **Development Mode (Hot Reload Server + Vite)**:
   ```bash
   npm run dev
   ```
   *(Runs `tsx server.ts` binding to port 3000)*
3. **Production Build (Bundles Server & Frontend)**:
   ```bash
   npm run build
   ```
   *(Builds Vite static assets and bundles `server.ts` to `dist/server.cjs` using esbuild)*
4. **Production Start**:
   ```bash
   npm start
   ```
   *(Runs `node dist/server.cjs` on port 3000 with Docker background notification worker active)*
5. **Type Check / Linter**:
   ```bash
   npm run lint
   ```

---

## 🐳 Docker Deployment
The project includes a ready-to-use `Dockerfile` and `docker-compose.yml`.
- Build image: `docker build -t vex-deals .`
- Run container: `docker run -p 3000:3000 -e GEMINI_API_KEY=your_key vex-deals`
