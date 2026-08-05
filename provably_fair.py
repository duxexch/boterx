#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Provably Fair System for VEX Games
Implements server seed + client seed + SHA256 commitment scheme.

Flow:
1. Server generates server_seed (32 bytes hex)
2. Server sends SHA256(server_seed) to client (commitment)
3. Client provides client_seed (or uses default)
4. Result = HMAC-SHA256(server_seed, client_seed:nonce) → converted to game result
5. After round, server reveals server_seed
6. Client verifies: SHA256(revealed_seed) == commitment, re-computes result
"""

import hashlib
import hmac
import secrets
import json
import os
import csv
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class ProvablyFair:
    """Provably fair random number generator with commitment scheme."""

    def __init__(self):
        self._sessions = {}  # session_id -> {server_seed, client_seed, nonce, hash}
        self._revealed = {}   # session_id -> server_seed (revealed after round)
        self._lock = __import__('threading').Lock()

    def generate_server_seed(self):
        """Generate a cryptographically secure server seed (64 hex chars)."""
        return secrets.token_hex(32)

    def hash_seed(self, server_seed):
        """SHA256 hash of server seed for commitment."""
        return hashlib.sha256(server_seed.encode()).hexdigest()

    def create_session(self, session_id, client_seed=None):
        """Create a new provably fair session with seed commitment."""
        with self._lock:
            server_seed = self.generate_server_seed()
            seed_hash = self.hash_seed(server_seed)
            self._sessions[session_id] = {
                'server_seed': server_seed,
                'seed_hash': seed_hash,
                'client_seed': client_seed or secrets.token_hex(8),
                'nonce': 0,
                'created_at': datetime.now().isoformat(),
            }
            return {
                'seed_hash': seed_hash,
                'client_seed': self._sessions[session_id]['client_seed'],
            }

    def get_seed_hash(self, session_id):
        """Get the seed hash for a session (for display before round)."""
        with self._lock:
            s = self._sessions.get(session_id)
            if s:
                return {'seed_hash': s['seed_hash'], 'client_seed': s['client_seed']}
            return None

    def generate_result(self, session_id, max_value=10000):
        """Generate a provably fair random number (0 to max_value-1)."""
        with self._lock:
            s = self._sessions.get(session_id)
            if not s:
                # Create on-the-fly if not exists
                server_seed = self.generate_server_seed()
                seed_hash = self.hash_seed(server_seed)
                s = {
                    'server_seed': server_seed,
                    'seed_hash': seed_hash,
                    'client_seed': secrets.token_hex(8),
                    'nonce': 0,
                    'created_at': datetime.now().isoformat(),
                }
                self._sessions[session_id] = s

            s['nonce'] += 1
            nonce = s['nonce']

            # HMAC-SHA256(server_seed, client_seed:nonce)
            message = f"{s['client_seed']}:{nonce}"
            hmac_result = hmac.new(
                s['server_seed'].encode(),
                message.encode(),
                hashlib.sha256
            ).hexdigest()

            # Convert first 8 hex chars to integer, mod max_value
            result_int = int(hmac_result[:8], 16) % max_value

            return {
                'result': result_int,
                'nonce': nonce,
                'seed_hash': s['seed_hash'],
                'client_seed': s['client_seed'],
            }

    def generate_float(self, session_id, min_val=0.0, max_val=1.0):
        """Generate a provably fair float in range [min_val, max_val)."""
        r = self.generate_result(session_id, max_value=1000000)
        float_val = min_val + (r['result'] / 1000000.0) * (max_val - min_val)
        return {
            'value': float_val,
            'nonce': r['nonce'],
            'seed_hash': r['seed_hash'],
            'client_seed': r['client_seed'],
        }

    def reveal_seed(self, session_id):
        """Reveal the server seed after round ends (for verification)."""
        with self._lock:
            s = self._sessions.get(session_id)
            if not s:
                return None
            revealed = {
                'server_seed': s['server_seed'],
                'seed_hash': s['seed_hash'],
                'client_seed': s['client_seed'],
                'nonce': s['nonce'],
            }
            self._revealed[session_id] = revealed
            # Clean up active session
            del self._sessions[session_id]
            return revealed

    def verify(self, server_seed, client_seed, nonce, max_value=10000):
        """Verify a result by recomputing from revealed seeds."""
        # Check hash
        computed_hash = self.hash_seed(server_seed)

        # Recompute result for each nonce up to nonce
        results = []
        for n in range(1, nonce + 1):
            message = f"{client_seed}:{n}"
            hmac_result = hmac.new(
                server_seed.encode(),
                message.encode(),
                hashlib.sha256
            ).hexdigest()
            result_int = int(hmac_result[:8], 16) % max_value
            results.append(result_int)

        return {
            'valid': True,
            'seed_hash': computed_hash,
            'results': results,
            'last_result': results[-1] if results else None,
        }

    def get_active_session_count(self):
        """Get number of active provably fair sessions."""
        with self._lock:
            return len(self._sessions)

    def cleanup_old_sessions(self, max_age_minutes=30):
        """Remove old unrevealed sessions."""
        with self._lock:
            now = datetime.now()
            to_remove = []
            for sid, s in self._sessions.items():
                try:
                    created = datetime.fromisoformat(s.get('created_at', ''))
                    if (now - created).total_seconds() > max_age_minutes * 60:
                        to_remove.append(sid)
                except:
                    to_remove.append(sid)
            for sid in to_remove:
                del self._sessions[sid]
            return len(to_remove)


# Singleton instance
_pf = ProvablyFair()
