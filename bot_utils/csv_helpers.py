"""
bot_utils/csv_helpers.py — CSV read/write helpers with thread-safe locking
Extracted from comprehensive_bot.py. Uses per-file threading.Lock.
"""
import csv
import os
import tempfile
import threading
from .constants import CSV_ENCODING

_csv_locks = {}

def get_csv_lock(filename):
    """الحصول على قفل لملف CSV محدد"""
    if filename not in _csv_locks:
        _csv_locks[filename] = threading.Lock()
    return _csv_locks[filename]

def safe_csv_write(filename, rows, fieldnames=None, mode='a'):
    """كتابة آمنة إلى ملف CSV مع قفل خيطي و كتابة ذرية"""
    lock = get_csv_lock(filename)
    with lock:
        try:
            # Write to temp file first, then atomic replace
            fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(filename) or '.', suffix='.tmp')
            with os.fdopen(fd, 'w', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if mode == 'w':
                    writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') if isinstance(row, dict) else row for k in fieldnames})
            os.replace(tmp_path, filename)
            return True
        except Exception as e:
            try:
                os.unlink(tmp_path)
            except:
                pass
            return False

def safe_csv_read(filename):
    """قراءة آمنة من ملف CSV مع قفل خيطي"""
    lock = get_csv_lock(filename)
    with lock:
        if not os.path.exists(filename):
            return []
        rows = []
        try:
            with open(filename, 'r', encoding=CSV_ENCODING) as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except Exception:
            return []
        return rows

def read_csv_simple(filename):
    """قراءة CSV بسيطة — ترجع list of dicts"""
    if not os.path.exists(filename):
        return []
    try:
        with open(filename, 'r', encoding=CSV_ENCODING) as f:
            return list(csv.DictReader(f))
    except Exception:
        return []
