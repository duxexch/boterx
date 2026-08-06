#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QA Matrix Generator — generates professional iGaming-level test cases
for any game using the Matrix Approach (Core × Environmental matrices).

Usage:
    python qa_matrix_generator.py

Output:
    qa_exports/Aviator_QA_TestCases.xlsx (400+ cases)
    qa_exports/Crash_QA_TestCases.xlsx (300+ cases)
    ... one Excel per game

Pattern: 40-50 Core Functional cases × Network/Telegram/Security/UI/Perf matrices
= 300-500 unique test cases per game, zero duplication.
"""
import os
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ============================================================
# ENVIRONMENTAL MATRICES (reusable across all games)
# ============================================================

NETWORK_MATRIX = [
    {"suffix": "during Offline", "type": "Network", "steps": "1. Disconnect network\n2. Perform action", "expected": "Action is queued or rejected gracefully. 'Network Disconnected' overlay shown. No data corruption", "priority": "High", "severity": "High"},
    {"suffix": "during Slow 3G", "type": "Network", "steps": "1. Throttle to Slow 3G (400ms latency)\n2. Perform action", "expected": "Action completes with delay. Animation doesn't freeze. No timeout errors", "priority": "Medium", "severity": "Medium"},
    {"suffix": "during Packet Loss", "type": "Network", "steps": "1. Set 30% packet loss\n2. Perform action", "expected": "Auto-retry or graceful degradation. SSE reconnects. No stuck state", "priority": "High", "severity": "High"},
    {"suffix": "after Reconnect", "type": "Network", "steps": "1. Disconnect\n2. Wait 5s\n3. Reconnect", "expected": "Game resyncs to current state. Bet/round status preserved. Multiplier jumps to server value", "priority": "Critical", "severity": "Critical"},
    {"suffix": "during Timeout", "type": "Network", "steps": "1. Set server timeout to 1s\n2. Perform action", "expected": "Client shows 'Request timeout' toast. Retry button appears. No silent failure", "priority": "High", "severity": "High"},
]

TELEGRAM_MATRIX = [
    {"suffix": "via TMA MainButton", "type": "Telegram Mini App", "steps": "1. Use Telegram MainButton for action", "expected": "Action triggers correctly via TMA SDK. Button text updates to next state", "priority": "High", "severity": "High"},
    {"suffix": "via TMA BackButton", "type": "Telegram Mini App", "steps": "1. Click TMA BackButton during action", "expected": "Confirm exit dialog shown, or action cancelled. NOT browser default back", "priority": "High", "severity": "High"},
    {"suffix": "after TMA Theme Change", "type": "Telegram Mini App", "steps": "1. Change TMA theme mid-action\n2. Observe UI", "expected": "Colors update without breaking state. Game continues without reset", "priority": "Medium", "severity": "Medium"},
    {"suffix": "after TMA Resume from Background", "type": "Telegram Mini App", "steps": "1. Minimize TMA\n2. Wait 30s\n3. Resume", "expected": "Game resyncs to current round state. No stale multiplier. Bet status preserved", "priority": "Critical", "severity": "Critical"},
    {"suffix": "within TMA Safe Area", "type": "Telegram Mini App", "steps": "1. Open on notched device\n2. Check all UI elements", "expected": "No element overlaps notch or TMA header/footer. Bottom row visible above MainButton", "priority": "Medium", "severity": "Medium"},
]

SECURITY_MATRIX = [
    {"suffix": "with Replay Attack", "type": "Security", "steps": "1. Intercept action packet\n2. Replay it 3 times", "expected": "Server rejects duplicates (409 Conflict). Only first action processed. Balance unchanged after 1st", "priority": "Critical", "severity": "Critical"},
    {"suffix": "with Invalid JWT", "type": "Security", "steps": "1. Expire/corrupt session token\n2. Perform action", "expected": "401 Unauthorized. Game redirects to re-auth. No balance change", "priority": "Critical", "severity": "Critical"},
    {"suffix": "after Session Expired", "type": "Security", "steps": "1. Wait for session to expire\n2. Perform action", "expected": "Session refresh or re-login prompt. No silent acceptance of expired session", "priority": "High", "severity": "High"},
    {"suffix": "with Rate Limit Exceeded", "type": "Security", "steps": "1. Send 20 requests in 1s\n2. Perform action on 21st", "expected": "429 Too Many Requests. 'طلبات كثيرة' toast shown. No DoS", "priority": "High", "severity": "High"},
    {"suffix": "with Duplicate Payload", "type": "Security", "steps": "1. Send same request_id twice", "expected": "Second request rejected (409). request_id dedup works correctly", "priority": "Critical", "severity": "Critical"},
]

UI_MATRIX = [
    {"suffix": "in Landscape", "type": "UI", "steps": "1. Rotate device to landscape\n2. Perform action", "expected": "Layout scales. No truncation. Canvas/game area fills screen", "priority": "Medium", "severity": "Medium"},
    {"suffix": "in Dark Mode", "type": "UI", "steps": "1. Switch to dark theme\n2. Perform action", "expected": "Colors update. Text readable. No white-on-white or invisible elements", "priority": "Medium", "severity": "Medium"},
    {"suffix": "in RTL (Arabic)", "type": "UI", "steps": "1. Set language to Arabic\n2. Perform action", "expected": "Layout is RTL. Text direction correct. No LTR artifacts. Numbers LTR acceptable", "priority": "Medium", "severity": "Medium"},
    {"suffix": "on Low-End Device", "type": "UI", "steps": "1. Throttle CPU 4x slowdown\n2. Perform action", "expected": "FPS >= 30. No freeze. Animation degrades gracefully (reduces particles)", "priority": "High", "severity": "High"},
    {"suffix": "on Small Screen (320px)", "type": "UI", "steps": "1. Set viewport to 320px width\n2. Perform action", "expected": "All buttons visible. No horizontal scroll. Bet input accessible. Canvas scales", "priority": "Medium", "severity": "Medium"},
]

PERFORMANCE_MATRIX = [
    {"suffix": "with Low Memory", "type": "Performance", "steps": "1. Simulate low memory\n2. Perform 50 rounds", "expected": "No OOM crash. GC kicks in. Game recovers. Memory stable after 50 rounds", "priority": "High", "severity": "High"},
    {"suffix": "with 100 concurrent players (SSE)", "type": "Performance", "steps": "1. Connect 100 SSE clients\n2. Play 10 rounds", "expected": "Server handles within 2GB/1core. SSE delivers <2s latency. No 502/503", "priority": "Critical", "severity": "Critical"},
]

ALL_MATRICES = NETWORK_MATRIX + TELEGRAM_MATRIX + SECURITY_MATRIX + UI_MATRIX + PERFORMANCE_MATRIX

# ============================================================
# GAME-SPECIFIC CORE TEST CASES
# ============================================================

AVIATOR_CORE = [
    # --- Round Lifecycle ---
    {"module": "Game Engine", "feature": "Round Lifecycle", "title": "Verify round starts with 6s countdown", "pre": "User in game, no active round", "steps": "1. Wait for previous round to end\n2. Observe countdown", "expected": "Countdown starts at 6, decrements each second. 'ضع رهانك' message shown", "priority": "Critical", "severity": "Critical"},
    {"module": "Game Engine", "feature": "Round Lifecycle", "title": "Verify multiplier starts at 1.00x and increments", "pre": "Countdown reached 0", "steps": "1. Observe multiplier after countdown", "expected": "Multiplier starts at 1.00x, increments smoothly. Plane takes off at 22° angle", "priority": "Critical", "severity": "Critical"},
    {"module": "Game Engine", "feature": "Round Lifecycle", "title": "Verify slow growth phase (first 2s on runway)", "pre": "Round started", "steps": "1. Observe multiplier for first 2 seconds", "expected": "Multiplier increments slowly (GROWTH=1.003). Numbers move slowly. Plane on runway", "priority": "High", "severity": "High"},
    {"module": "Game Engine", "feature": "Round Lifecycle", "title": "Verify fast growth phase (after 2s)", "pre": "2 seconds elapsed", "steps": "1. Observe multiplier after 2s mark", "expected": "Growth rate increases (GROWTH=1.012). Multiplier accelerates. Plane climbs", "priority": "High", "severity": "High"},
    {"module": "Game Engine", "feature": "Crash", "title": "Verify crash ends the round", "pre": "Round in progress", "steps": "1. Wait for crash point\n2. Observe crash", "expected": "💥 message shown. Crash point displayed. Plane disappears. All un-cashed bets lost", "priority": "Critical", "severity": "Critical"},
    {"module": "Game Engine", "feature": "Crash", "title": "Verify crash shows total distributed profits", "pre": "Round crashed", "steps": "1. Read post-crash message", "expected": "'💰 إجمالي الأرباح الموزعة: X — Y لاعب ربح من Z' shown for 5 seconds", "priority": "Medium", "severity": "Medium"},
    {"module": "Game Engine", "feature": "Round Lifecycle", "title": "Verify new round starts automatically after crash", "pre": "Crash results shown", "steps": "1. Wait 5 seconds after crash", "expected": "New countdown begins at 6. Plane returns to runway. History bar updated", "priority": "Critical", "severity": "Critical"},

    # --- Betting ---
    {"module": "Betting", "feature": "Place Bet", "title": "Verify placing valid bet during countdown", "pre": "Balance=100, countdown active", "steps": "1. Enter 10 in bet field\n2. Click Bet button", "expected": "10 deducted. Button shows 'إلغاء'. Bet appears in my bets panel. Balance=90", "priority": "Critical", "severity": "Critical"},
    {"module": "Betting", "feature": "Cancel Bet", "title": "Verify cancelling bet before takeoff", "pre": "Bet placed, countdown active", "steps": "1. Click 'إلغاء' button", "expected": "Bet cancelled. 10 refunded. Button reverts to 'رهان'. Balance=100", "priority": "Critical", "severity": "Critical"},
    {"module": "Betting", "feature": "Place Bet", "title": "Verify bet rejected after countdown ends", "pre": "Countdown=0, plane flying", "steps": "1. Click Bet button", "expected": "Toast: '⏳ انتظر نهاية الجولة الحالية!'. No bet placed. Balance unchanged", "priority": "Critical", "severity": "Critical"},
    {"module": "Betting", "feature": "Place Bet", "title": "Verify insufficient balance shows deposit modal", "pre": "Balance=0", "steps": "1. Enter 10 in bet field\n2. Click Bet", "expected": "VEX deposit modal appears. No bet placed. No crash", "priority": "High", "severity": "High"},
    {"module": "Betting", "feature": "Dual Slots", "title": "Verify two simultaneous bets (slot 1 + slot 2)", "pre": "Balance=100", "steps": "1. Enable slot 2\n2. Bet 10 on slot 1\n3. Bet 20 on slot 2", "expected": "Both bets accepted. 30 deducted. Both appear in my bets. Balance=70", "priority": "High", "severity": "High"},
    {"module": "Betting", "feature": "Dual Slots", "title": "Verify slot 2 toggle disables/enables", "pre": "Slot 2 disabled", "steps": "1. Toggle slot 2 on\n2. Toggle slot 2 off", "expected": "Button enables/disables. Input field shows/hides. No orphan state", "priority": "Medium", "severity": "Medium"},

    # --- Cash Out ---
    {"module": "Betting", "feature": "Cash Out", "title": "Verify manual cash out at current multiplier", "pre": "Active bet=10, multiplier=2.50x", "steps": "1. Click 'سحب' button", "expected": "Win=25 (10×2.50). Balance updates. Button shows '✓ 25'. 🪂 parachute with name+amount", "priority": "Critical", "severity": "Critical"},
    {"module": "Betting", "feature": "Cash Out", "title": "Verify bet button shows increasing amount during flight", "pre": "Active bet=10, multiplier rising", "steps": "1. Observe button text during flight", "expected": "Button shows '💰 12' → '💰 18' → '💰 25' — updates with multiplier", "priority": "High", "severity": "High"},
    {"module": "Betting", "feature": "Auto Cash Out", "title": "Verify auto cash out at target multiplier", "pre": "Active bet=10, Auto Cashout=5x", "steps": "1. Start round\n2. Wait for 5.00x", "expected": "Cash out auto-triggers at exactly 5.00x. Payout=50. Parachute appears", "priority": "High", "severity": "High"},
    {"module": "Betting", "feature": "Cash Out", "title": "Verify cash out rejected if already crashed", "pre": "Multiplier crashed at 2x", "steps": "1. Click 'سحب' after crash", "expected": "Request rejected by server. 'انفجرت الطائرة' message. No payout. Balance unchanged", "priority": "Critical", "severity": "Critical"},

    # --- Provably Fair ---
    {"module": "Provably Fair", "feature": "Seed Hash", "title": "Verify seed_hash is broadcast before betting window", "pre": "New round starting", "steps": "1. Observe waiting message\n2. Check for seed_hash field", "expected": "seed_hash (64-char hex) present in SSE waiting message BEFORE bets open", "priority": "Critical", "severity": "Critical"},
    {"module": "Provably Fair", "feature": "Server Seed Reveal", "title": "Verify server_seed revealed after crash", "pre": "Round crashed", "steps": "1. Read crash SSE message\n2. Check for server_seed field", "expected": "server_seed (64-char hex) present in crash message. SHA256(server_seed) matches seed_hash", "priority": "Critical", "severity": "Critical"},
    {"module": "Provably Fair", "feature": "Verification", "title": "Verify crash point matches HMAC-SHA256 calculation", "pre": "server_seed + client_seed revealed", "steps": "1. Calculate HMAC-SHA256(server_seed, client_seed:round_id)\n2. Convert to crash point\n3. Compare with displayed crash", "expected": "Calculated crash point matches server-announced crash point exactly", "priority": "Critical", "severity": "Critical"},

    # --- UI / Animation ---
    {"module": "UI", "feature": "Plane Animation", "title": "Verify plane takes off at 22° angle", "pre": "Round started", "steps": "1. Observe plane trajectory for first 3.5s", "expected": "Plane moves from bottom-left to center at ~22° angle, then hovers. Background scrolls", "priority": "Medium", "severity": "Medium"},
    {"module": "UI", "feature": "Weather", "title": "Verify random weather each round", "pre": "Multiple rounds played", "steps": "1. Play 5 rounds\n2. Observe sky background", "expected": "Sky changes randomly: day (blue+clouds), night (stars+moon), storm (rain+lightning)", "priority": "Low", "severity": "Low"},
    {"module": "UI", "feature": "Parachute", "title": "Verify parachute shows player name + amount", "pre": "Player cashed out", "steps": "1. Observe parachute after cashout", "expected": "🪂 icon + gold pill with '+250' + player name below. Disappears after 3s", "priority": "Medium", "severity": "Medium"},
    {"module": "UI", "feature": "Connection Indicator", "title": "Verify connection indicator updates", "pre": "Game loaded", "steps": "1. Observe topbar\n2. Disconnect network\n3. Reconnect", "expected": "🟢 connected → 🔴 disconnected → 🟡 reconnecting → 🟢 connected", "priority": "High", "severity": "High"},
    {"module": "UI", "feature": "History Bar", "title": "Verify history bar updates after each round", "pre": "Round completed", "steps": "1. Observe history bar", "expected": "New crash point added to left. Color: green if ≥1.5x, red if <1.5x. Max 15 items", "priority": "Medium", "severity": "Medium"},

    # --- Wallet Sync ---
    {"module": "Wallet", "feature": "Balance Sync", "title": "Verify balance updates after bet", "pre": "Balance=100", "steps": "1. Place bet=10", "expected": "Balance pill flashes red, updates to 90 immediately", "priority": "High", "severity": "High"},
    {"module": "Wallet", "feature": "Balance Sync", "title": "Verify balance updates after cashout", "pre": "Active bet, multiplier=3x", "steps": "1. Cash out", "expected": "Balance pill flashes green, updates with payout. Matches server balance_after", "priority": "High", "severity": "High"},
    {"module": "Wallet", "feature": "Balance Sync", "title": "Verify balance polls every 5 seconds", "pre": "Idle (no bet)", "steps": "1. Admin approves deposit\n2. Wait 5s", "expected": "Balance updates to new value within 5s without manual refresh", "priority": "Medium", "severity": "Medium"},

    # --- Edge Cases ---
    {"module": "Game Engine", "feature": "Edge Case", "title": "Verify instant crash at 1.00x", "pre": "Round started", "steps": "1. Observe if crash_point=1.00", "expected": "Plane takes off and immediately crashes at 1.00x. All bets lost. History shows 1.00x", "priority": "High", "severity": "High"},
    {"module": "Game Engine", "feature": "Edge Case", "title": "Verify very high crash point (50x+)", "pre": "Round started", "steps": "1. Wait for high multiplier\n2. Observe", "expected": "Multiplier continues. No cap. Background darkens. Stars appear. No performance drop", "priority": "Medium", "severity": "Medium"},
    {"module": "Betting", "feature": "Edge Case", "title": "Verify bet amount=0 rejected", "pre": "Countdown active", "steps": "1. Enter 0 in bet field\n2. Click Bet", "expected": "No action taken. Button does not submit. No deduction", "priority": "Medium", "severity": "Medium"},
    {"module": "Betting", "feature": "Edge Case", "title": "Verify bet exceeds max (5000) rejected", "pre": "Countdown active", "steps": "1. Enter 99999 in bet field\n2. Click Bet", "expected": "Bet rejected or capped at 5000. Error message shown", "priority": "Medium", "severity": "Medium"},

    # --- Race Conditions ---
    {"module": "Betting", "feature": "Race Condition", "title": "Verify double-clicking Bet button rapidly", "pre": "Countdown active, Balance=100", "steps": "1. Click Bet 5 times in 100ms", "expected": "Only 1 bet placed (server dedup via request_id). Balance=90, not 50", "priority": "Critical", "severity": "Critical"},
    {"module": "Betting", "feature": "Race Condition", "title": "Verify double-clicking Cash Out rapidly", "pre": "Active bet, multiplier=3x", "steps": "1. Click Cash Out 5 times in 100ms", "expected": "Only 1 cashout processed. No double payout. Server rejects duplicates (409)", "priority": "Critical", "severity": "Critical"},
    {"module": "Betting", "feature": "Race Condition", "title": "Verify bet at exact timer=0 boundary", "pre": "Countdown at 0.01s", "steps": "1. Click Bet as timer hits 0", "expected": "Server uses server_ts to decide. If within window: accepted. If late: rejected with 'انتهت نافذة الرهان'", "priority": "Critical", "severity": "Critical"},
    {"module": "Betting", "feature": "Race Condition", "title": "Verify cashout at exact crash boundary", "pre": "Multiplier approaching crash_point", "steps": "1. Click Cash Out at same moment as crash", "expected": "Server checks mult vs crash_point. If mult < crash: win. If mult ≥ crash: rejected", "priority": "Critical", "severity": "Critical"},

    # --- Error Handling ---
    {"module": "Error Handling", "feature": "Server Error", "title": "Verify behavior when server returns 500", "pre": "Game in progress", "steps": "1. Simulate 500 error\n2. Observe UI", "expected": "Error toast shown. Game continues with last known state. No crash. Retry on next SSE", "priority": "High", "severity": "High"},
    {"module": "Error Handling", "feature": "SSE Disconnect", "title": "Verify behavior when SSE stream drops", "pre": "Game in progress", "steps": "1. Kill SSE connection\n2. Observe", "expected": "Indicator turns 🔴. Auto-reconnect after 2s. State fetches from /api/aviator/state", "priority": "High", "severity": "High"},

    # --- Audit Trail ---
    {"module": "Database", "feature": "Audit Trail", "title": "Verify round logged in aviator_rounds table", "pre": "Round completed", "steps": "1. Query SQLite aviator_rounds table\n2. Check latest entry", "expected": "round_id, crash_point, seed_hash, client_seed, server_seed, bet_count, totals all present", "priority": "Medium", "severity": "Medium"},

    # --- Multi-Device ---
    {"module": "Multi-Device", "feature": "Sync", "title": "Verify same round visible on 2 devices", "pre": "2 devices logged in", "steps": "1. Open Aviator on Device A\n2. Open Aviator on Device B\n3. Observe multiplier", "expected": "Both show same multiplier at same time. Same crash point. Same countdown", "priority": "High", "severity": "High"},
    {"module": "Multi-Device", "feature": "Bet Independence", "title": "Verify bet on Device A doesn't affect Device B", "pre": "Same user on 2 devices", "steps": "1. Place bet on Device A\n2. Check Device B", "expected": "Device B shows no active bet. Each device has independent bet state", "priority": "Medium", "severity": "Medium"},
]

# ============================================================
# GENERATION ENGINE
# ============================================================

def generate_excel(game_name, game_prefix, core_cases, matrices, output_dir="qa_exports"):
    """Generate Excel file with Core + Matrix-expanded test cases."""
    os.makedirs(output_dir, exist_ok=True)
    final_cases = []
    test_counter = 1

    # 1. Add Core Functional cases
    for case in core_cases:
        final_cases.append({
            "Test ID": f"{game_prefix}-FUNC-{test_counter:03d}",
            "Module": case["module"],
            "Feature": case["feature"],
            "Test Title": case["title"],
            "Preconditions": case["pre"],
            "Test Steps": case["steps"],
            "Expected Result": case["expected"],
            "Priority": case["priority"],
            "Severity": case["severity"],
            "Test Type": case.get("type_override", "Functional"),
            "Status": "Draft",
            "Notes": "",
        })
        test_counter += 1

    # 2. Expand each Core case × each Matrix
    for matrix in matrices:
        for case in core_cases:
            # Skip illogical combos
            if case["module"] == "Provably Fair" and matrix["type"] == "Performance":
                continue
            if case["module"] == "Database" and matrix["type"] in ("UI", "Telegram Mini App"):
                continue

            cat_prefix = matrix["type"][:4].upper()
            final_cases.append({
                "Test ID": f"{game_prefix}-{cat_prefix}-{test_counter:03d}",
                "Module": case["module"],
                "Feature": case["feature"],
                "Test Title": f"{case['title']} {matrix['suffix']}",
                "Preconditions": case["pre"],
                "Test Steps": f"{case['steps']}\n--- Matrix ---\n{matrix['steps']}",
                "Expected Result": f"{matrix['expected']}\n(Original: {case['expected']})",
                "Priority": matrix["priority"],
                "Severity": matrix["severity"],
                "Test Type": matrix["type"],
                "Status": "Draft",
                "Notes": "Auto-generated via Matrix Approach",
            })
            test_counter += 1

    # 3. Write to Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"{game_name} QA"

    # Headers
    headers = ["Test ID", "Module", "Feature", "Test Title", "Preconditions",
               "Test Steps", "Expected Result", "Priority", "Severity",
               "Test Type", "Status", "Notes"]

    # Style headers
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="1E40AF", end_color="1E40AF", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin_border = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin")
    )

    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border

    # Data rows
    priority_colors = {
        "Critical": PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid"),
        "High": PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid"),
        "Medium": PatternFill(start_color="DBEAFE", end_color="DBEAFE", fill_type="solid"),
        "Low": PatternFill(start_color="F3F4F6", end_color="F3F4F6", fill_type="solid"),
    }

    for row_idx, case in enumerate(final_cases, 2):
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=case.get(header, ""))
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = thin_border
            if header == "Priority":
                fill = priority_colors.get(case.get("Priority", ""), None)
                if fill:
                    cell.fill = fill
                    cell.font = Font(bold=True)

    # Column widths
    widths = {"A": 16, "B": 14, "C": 16, "D": 40, "E": 28, "F": 36, "G": 40, "H": 10, "I": 10, "J": 16, "K": 8, "L": 20}
    for col_letter, width in widths.items():
        ws.column_dimensions[col_letter].width = width

    # Freeze header row
    ws.freeze_panes = "A2"

    # Auto-filter
    ws.auto_filter.ref = f"A1:L{len(final_cases) + 1}"

    filepath = os.path.join(output_dir, f"{game_name}_QA_TestCases.xlsx")
    wb.save(filepath)
    print(f"[OK] {game_name}: {len(final_cases)} test cases -> {filepath}")
    return len(final_cases)


# ============================================================
# RUN — Generate for all games
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("QA Matrix Generator — Boterx VEX Games")
    print("=" * 60)

    total = 0

    # Aviator
    total += generate_excel("Aviator", "AVI", AVIATOR_CORE, ALL_MATRICES)

    print(f"\n{'=' * 60}")
    print(f"TOTAL: {total} test cases generated")
    print(f"Files in: qa_exports/")
    print(f"\nTo add more games: define CORE cases list + call generate_excel()")
    print(f"Pattern: {len(AVIATOR_CORE)} Core × {len(ALL_MATRICES)} Matrices = {len(AVIATOR_CORE) * len(ALL_MATRICES) + len(AVIATOR_CORE)} cases")
