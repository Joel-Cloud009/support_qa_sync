"""
duc_support_qa → Supabase 증분 동기화
사용법: python sync_support_qa.py

동작:
1. Supabase에서 저장된 마지막 writedate(watermark) 조회
2. Redshift에서 writedate > watermark 인 신규 행만 조회
3. Supabase에 upsert (qaidx 기준, 중복 시 덮어씀)

환경변수:
- SUPABASE_URL (필수): 예) https://xxxx.supabase.co
- SUPABASE_SERVICE_KEY (필수): service_role key (RLS 우회, 쓰기 권한)
- REDSHIFT_HOST/PORT/DBNAME/USER/PASSWORD (필수): Redshift 접속 정보
"""

import json
import os
import sys
import urllib.request
import urllib.parse

import psycopg2
import psycopg2.extras


def _load_conn():
    host = os.environ.get("REDSHIFT_HOST")
    if not host:
        print("[오류] REDSHIFT_HOST 등 Redshift 접속 환경변수가 필요합니다.", file=sys.stderr)
        sys.exit(2)
    return dict(
        host=host,
        port=int(os.environ.get("REDSHIFT_PORT", 5439)),
        dbname=os.environ.get("REDSHIFT_DBNAME", ""),
        user=os.environ.get("REDSHIFT_USER", ""),
        password=os.environ.get("REDSHIFT_PASSWORD", ""),
        connect_timeout=30,
        options="-c statement_timeout=600000",
    )

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
DEFAULT_WATERMARK = "2026-01-01 07:00:00"

COLUMNS = [
    "qaidx", "platform", "useridx", "facebookid", "name", "contents",
    "device", "os_version", "mobile_version", "writedate", "categoryidx", "is_issue_sentence",
]


def _headers():
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _require_config():
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("[오류] SUPABASE_URL / SUPABASE_SERVICE_KEY 환경변수가 필요합니다.", file=sys.stderr)
        sys.exit(2)


def get_watermark():
    qs = urllib.parse.urlencode({"select": "writedate", "order": "writedate.desc", "limit": "1"})
    url = f"{SUPABASE_URL}/rest/v1/support_qa?{qs}"
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
        if rows:
            return str(rows[0]["writedate"])
    except Exception as e:
        print(f"[경고] watermark 조회 실패, 기본값 사용: {e}", file=sys.stderr)
    return DEFAULT_WATERMARK


def fetch_new_rows(watermark):
    conn_info = _load_conn()
    conn = psycopg2.connect(**conn_info)
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    sql = f"""
        SELECT {', '.join(COLUMNS)}
        FROM duc_support_qa
        WHERE writedate > '{watermark}'
        ORDER BY writedate
    """
    cur.execute(sql)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(zip(COLUMNS, [str(v) if v is not None else None for v in row])) for row in rows]


def upsert_rows(rows):
    url = f"{SUPABASE_URL}/rest/v1/support_qa"
    headers = _headers()
    headers["Prefer"] = "resolution=merge-duplicates"
    data = json.dumps(rows).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        resp.read()


def main():
    _require_config()

    watermark = get_watermark()
    print(f"[watermark] {watermark}", file=sys.stderr)

    rows = fetch_new_rows(watermark)
    print(f"[조회] 신규 행 {len(rows)}건", file=sys.stderr)

    if not rows:
        print("[완료] 신규 데이터 없음")
        return

    CHUNK = 500
    for i in range(0, len(rows), CHUNK):
        upsert_rows(rows[i:i + CHUNK])

    print(f"[완료] {len(rows)}건 upsert")


if __name__ == "__main__":
    main()
