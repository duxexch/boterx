# Autonomous Game Surgeon Protocol — Permanent Command

> **أمر دائم**: يُطبّق على أي لعبة عند الطلب. لا حاجة لإعادة كتابته.
> القيادة: "Apply Surgeon Protocol to [Game Name]"
> أو للاستخدام العام: "نفّذ بروتوكول الجراح على [اسم اللعبة]"

---

## PHASE 1: DEEP ANALYSIS & AUDIT (The Diagnosis)
1. Read the entire codebase for the target game (Frontend HTML/JS/CSS, Backend app.py endpoints, game_engine.py).
2. Map the current State Machine. Identify any invalid state transitions.
3. Hunt for Edge Cases: Race conditions, Float precision errors, Unhandled promise rejections, Missing error boundaries.
4. Audit UI/UX: Static elements, missing responsive breakpoints, lack of 3D depth, non-semantic HTML, missing TMA safe areas.

## PHASE 2: LOGIC FORTIFICATION (The Cure)
- Strict State Machine: NO action can fire if it violates state rules.
- Idempotency & Security: EVERY state-changing API call MUST generate UUID. Backend MUST reject duplicates.
- Network Resilience: Auto-reconnect. Offline Outbox for critical actions.
- Wallet ACID: ALL financial math MUST use Decimal. NO float for money.

## PHASE 3: 3D & RESPONSIVE UI REVOLUTION (The Enhancement)
- 3D & Physics: Elements must have depth (perspective, rotateX/Y, translateZ).
- Micro-interactions: Haptic feedback, sound triggers, fluid motion on EVERY state change.
- Bulletproof Responsive: CSS Grid + clamp(). Test: 320px, 430px, 768px, 1920px.
- Cross-Browser: Standard properties with fallbacks. Fix 100vh → dvh.
- Telegram Mini App: safeAreaInset padding, BackButton intercept, MainButton sync.

## PHASE 4: PROACTIVE GAP FILLING (The Mind)
Build anything missing: Loading skeletons, toast notifications, provably fair UI, auto-play limits, theme sync.

## PHASE 5: AUTONOMOUS VERIFICATION LOOP (The Closure)
1. Write tests covering Race Conditions, Network Drops, State Violations.
2. Execute tests via terminal.
3. Analyze failures → fix → re-run.
4. Repeat until 100% Green.
5. Final Report: What was fixed, what was added, confirm game is permanently closed.

---

## Games Status (as of 2026-08-07)
| Game | Protocol Status | Notes |
|---|---|---|
| Aviator | Ready for Surgeon | Global round, provably fair, ACID, offline outbox done. Needs 3D UI + tests. |
| Crash | Ready | Similar to Aviator. |
| Mines | Ready | Grid reveal, needs provably fair UI + tests. |
| Plinko | Ready | Physics, needs ACID wiring for /end. |
| LuckyWheel | Ready | Canvas spin, needs tests. |
| Lottery | Ready | Ticket draw, provably fair done. |
| Snatch | Ready | Catch gift, needs tests. |