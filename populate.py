#!/usr/bin/env python3
"""
Populate whoismytd PostgreSQL database from Oireachtas Open Data API.
Ingests 34th Dáil members, parties, constituencies, bills, divisions, and votes.

Usage:
  docker compose up -d        # start Postgres
  python populate.py          # fill database
  psql $DATABASE_URL         # inspect data
"""

import os
import sys
import requests
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime
from dotenv import load_dotenv
import time

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')
OIREACHTAS_API = 'https://api.oireachtas.ie/v1'

if not DATABASE_URL:
    print("Error: DATABASE_URL not set in .env or environment")
    sys.exit(1)

conn = None

def log_step(msg):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}")

def log_result(label, count):
    print(f"  ✓ {label:<30} {count:>6,} rows")

def api_get(url, params, max_retries=3):
    """Make GET request with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 503:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"    ⏳ API busy, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
            response.raise_for_status()
            return response
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"    ⏳ Timeout, retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            raise
    return response

def create_tables():
    """Create all tables with full 34th Dáil schema."""
    log_step("Creating database tables")

    sql = """
    CREATE TABLE IF NOT EXISTS constituencies (
      id   SERIAL PRIMARY KEY,
      code VARCHAR(150) UNIQUE NOT NULL,
      name VARCHAR(250) NOT NULL
    );

    CREATE TABLE IF NOT EXISTS parties (
      id   SERIAL PRIMARY KEY,
      code VARCHAR(150) UNIQUE NOT NULL,
      name VARCHAR(250) NOT NULL
    );

    CREATE TABLE IF NOT EXISTS members (
      id               SERIAL PRIMARY KEY,
      pid              VARCHAR(250) UNIQUE NOT NULL,
      full_name        VARCHAR(300) NOT NULL,
      first_name       VARCHAR(200),
      last_name        VARCHAR(200),
      gender           VARCHAR(50),
      constituency_id  INT REFERENCES constituencies(id),
      party_id         INT REFERENCES parties(id),
      date_start       DATE,
      date_end         DATE,
      is_active        BOOLEAN DEFAULT TRUE,
      image_url        TEXT
    );

    CREATE TABLE IF NOT EXISTS bills (
      id               SERIAL PRIMARY KEY,
      bill_id          VARCHAR(300) UNIQUE NOT NULL,
      title            VARCHAR(600) NOT NULL,
      description      TEXT,
      bill_type        VARCHAR(150),
      bill_status      VARCHAR(150),
      date_introduced  DATE,
      uri              TEXT
    );

    CREATE TABLE IF NOT EXISTS divisions (
      id              SERIAL PRIMARY KEY,
      division_id     VARCHAR(300) UNIQUE NOT NULL,
      bill_id         INT REFERENCES bills(id),
      title           VARCHAR(600),
      date            DATE,
      ta_count        INT DEFAULT 0,
      nil_count       INT DEFAULT 0,
      staon_count     INT DEFAULT 0,
      result          VARCHAR(50),
      uri             TEXT
    );

    CREATE TABLE IF NOT EXISTS member_votes (
      id          SERIAL PRIMARY KEY,
      member_id   INT REFERENCES members(id) ON DELETE CASCADE,
      division_id INT REFERENCES divisions(id) ON DELETE CASCADE,
      vote        VARCHAR(10) NOT NULL CHECK (vote IN ('Tá', 'Níl', 'Staon')),
      UNIQUE (member_id, division_id)
    );

    CREATE INDEX IF NOT EXISTS idx_members_pid ON members(pid);
    CREATE INDEX IF NOT EXISTS idx_members_constituency ON members(constituency_id);
    CREATE INDEX IF NOT EXISTS idx_members_party ON members(party_id);
    CREATE INDEX IF NOT EXISTS idx_divisions_bill ON divisions(bill_id);
    CREATE INDEX IF NOT EXISTS idx_member_votes_member ON member_votes(member_id);
    CREATE INDEX IF NOT EXISTS idx_member_votes_division ON member_votes(division_id);
    """

    cursor = conn.cursor()
    for statement in sql.split(';'):
        if statement.strip():
            cursor.execute(statement)
    conn.commit()
    cursor.close()
    print("  ✓ Tables created")

def parse_date(date_str):
    """Parse ISO date string to date object, return None on failure."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str).date()
    except:
        return None

def fetch_members():
    """Fetch all 34th Dáil members and upsert to DB."""
    log_step("Fetching members from Oireachtas API")

    cursor = conn.cursor()
    skip = 0
    total = 0
    constituencies_seen = {}
    parties_seen = {}

    while True:
        response = api_get(f'{OIREACHTAS_API}/members', {
            'house': 'dail',
            'chamberNo': '34',
            'limit': 250,
            'skip': skip
        })
        data = response.json()
        results = data.get('results', [])

        if not results:
            break

        for item in results:
            member = item.get('member', {})
            pid = member.get('pId', '')
            full_name = member.get('fullName', member.get('showAs', '')).strip()

            if not pid or not full_name:
                continue

            first_name = member.get('firstName', '').strip() or None
            last_name = member.get('lastName', '').strip() or None
            gender = member.get('gender', '').strip() or None
            image_url = member.get('image_url') or None

            const_id = None
            const_name = None
            party_id = None
            party_name = None
            date_start = None
            date_end = None

            memberships = member.get('memberships', [])
            for membership in memberships:
                mem = membership.get('membership', {})
                house = mem.get('house', {})

                if house.get('houseNo') != '34':
                    continue

                date_start = parse_date(mem.get('dateRange', {}).get('start'))
                date_end = parse_date(mem.get('dateRange', {}).get('end'))

                represents = mem.get('represents', [])
                if represents:
                    const_name = represents[0].get('represent', {}).get('showAs', '').strip()
                    const_code = represents[0].get('represent', {}).get('representCode', '').strip()

                    if const_name and const_code not in constituencies_seen:
                        cursor.execute(
                            'INSERT INTO constituencies (code, name) VALUES (%s, %s) ON CONFLICT (code) DO NOTHING',
                            (const_code, const_name)
                        )
                        constituencies_seen[const_code] = True

                    cursor.execute('SELECT id FROM constituencies WHERE code = %s', (const_code,))
                    row = cursor.fetchone()
                    if row:
                        const_id = row[0]

                parties = mem.get('parties', [])
                if parties:
                    party_name = parties[0].get('party', {}).get('showAs', '').strip()
                    party_code = parties[0].get('party', {}).get('partyCode', '').strip()

                    if party_name and party_code not in parties_seen:
                        cursor.execute(
                            'INSERT INTO parties (code, name) VALUES (%s, %s) ON CONFLICT (code) DO NOTHING',
                            (party_code, party_name)
                        )
                        parties_seen[party_code] = True

                    cursor.execute('SELECT id FROM parties WHERE code = %s', (party_code,))
                    row = cursor.fetchone()
                    if row:
                        party_id = row[0]

                break

            cursor.execute('''
                INSERT INTO members (pid, full_name, first_name, last_name, gender,
                                      constituency_id, party_id, date_start, date_end, image_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (pid) DO UPDATE SET
                  full_name = EXCLUDED.full_name,
                  first_name = EXCLUDED.first_name,
                  last_name = EXCLUDED.last_name,
                  constituency_id = EXCLUDED.constituency_id,
                  party_id = EXCLUDED.party_id,
                  date_end = EXCLUDED.date_end
            ''', (pid, full_name, first_name, last_name, gender, const_id, party_id, date_start, date_end, image_url))

            total += 1

        skip += 250

    conn.commit()
    cursor.close()

    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM constituencies')
    const_count = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM parties')
    party_count = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM members')
    member_count = cursor.fetchone()[0]
    cursor.close()

    log_result('Constituencies', const_count)
    log_result('Parties', party_count)
    log_result('Members', member_count)

def fetch_bills():
    """Fetch all 34th Dáil bills and upsert to DB."""
    log_step("Fetching bills from Oireachtas API")

    cursor = conn.cursor()
    skip = 0
    total = 0

    while True:
        try:
            response = api_get(f'{OIREACHTAS_API}/legislation', {
                'house': 'dail',
                'chamberNo': '34',
                'limit': 250,
                'skip': skip
            })
            data = response.json()
            results = data.get('results', [])
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 422:
                break
            raise

        if not results:
            break

        for item in results:
            bill = item.get('bill', {})
            bill_id = bill.get('bill_id', '').strip()
            title = bill.get('title', '').strip()

            if not bill_id or not title:
                continue

            description = bill.get('description', '').strip() or None
            bill_type = bill.get('bill_type', '').strip() or None
            bill_status = bill.get('bill_status', '').strip() or None
            uri = bill.get('uri') or None
            date_introduced = None

            dates = bill.get('dates', [])
            for d in dates:
                if d.get('dateType') == 'intro':
                    date_introduced = parse_date(d.get('date'))
                    break

            cursor.execute('''
                INSERT INTO bills (bill_id, title, description, bill_type, bill_status, date_introduced, uri)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (bill_id) DO UPDATE SET
                  title = EXCLUDED.title,
                  description = EXCLUDED.description,
                  bill_type = EXCLUDED.bill_type,
                  bill_status = EXCLUDED.bill_status
            ''', (bill_id, title, description, bill_type, bill_status, date_introduced, uri))

            total += 1

        skip += 250

    conn.commit()
    cursor.close()

    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM bills')
    bill_count = cursor.fetchone()[0]
    cursor.close()

    log_result('Bills', bill_count)

def fetch_divisions():
    """Fetch all 34th Dáil divisions and upsert to DB."""
    log_step("Fetching divisions from Oireachtas API")

    cursor = conn.cursor()
    skip = 0
    total = 0

    while True:
        try:
            response = api_get(f'{OIREACHTAS_API}/divisions', {
                'house': 'dail',
                'chamberNo': '34',
                'limit': 250,
                'skip': skip
            })
            data = response.json()
            results = data.get('results', [])
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 422:
                print(f"  ℹ Reached end of pagination at skip={skip}")
                break
            raise

        if not results:
            break

        for item in results:
            division = item.get('division', {})
            division_id = division.get('division_id', '').strip()
            title = division.get('title', '').strip()
            date_str = division.get('date', '')
            uri = division.get('uri') or None

            if not division_id:
                continue

            date = parse_date(date_str)
            ta_count = len([v for v in division.get('member_votes', []) if v.get('vote') == 'Tá'])
            nil_count = len([v for v in division.get('member_votes', []) if v.get('vote') == 'Níl'])
            staon_count = len([v for v in division.get('member_votes', []) if v.get('vote') == 'Staon'])
            result = 'Passed' if ta_count > nil_count else 'Defeated' if nil_count > ta_count else 'Tied'

            bill_id_str = division.get('bill_id', '').strip()
            bill_id = None
            if bill_id_str:
                cursor.execute('SELECT id FROM bills WHERE bill_id = %s', (bill_id_str,))
                row = cursor.fetchone()
                if row:
                    bill_id = row[0]

            cursor.execute('''
                INSERT INTO divisions (division_id, bill_id, title, date, ta_count, nil_count, staon_count, result, uri)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (division_id) DO UPDATE SET
                  title = EXCLUDED.title,
                  ta_count = EXCLUDED.ta_count,
                  nil_count = EXCLUDED.nil_count,
                  staon_count = EXCLUDED.staon_count,
                  result = EXCLUDED.result
            ''', (division_id, bill_id, title, date, ta_count, nil_count, staon_count, result, uri))

            total += 1

        skip += 250

    conn.commit()
    cursor.close()

    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM divisions')
    division_count = cursor.fetchone()[0]
    cursor.close()

    log_result('Divisions', division_count)

def fetch_votes():
    """Fetch all member votes for each division and upsert to DB."""
    log_step("Fetching member votes from Oireachtas API")

    cursor = conn.cursor()
    cursor.execute('SELECT id, division_id FROM divisions')
    divisions = cursor.fetchall()
    cursor.close()

    total = 0

    for div_pk_id, div_id in divisions:
        response = requests.get(f'{OIREACHTAS_API}/divisions/{div_id}/votes', params={'limit': 200})
        response.raise_for_status()
        data = response.json()
        votes = data.get('results', [])

        cursor = conn.cursor()

        for vote_item in votes:
            vote = vote_item.get('vote', {})
            member_pid = vote.get('member_pid', '').strip()
            vote_value = vote.get('vote', '').strip()

            if not member_pid or vote_value not in ('Tá', 'Níl', 'Staon'):
                continue

            cursor.execute('SELECT id FROM members WHERE pid = %s', (member_pid,))
            member_row = cursor.fetchone()
            if not member_row:
                continue

            member_pk_id = member_row[0]

            cursor.execute('''
                INSERT INTO member_votes (member_id, division_id, vote)
                VALUES (%s, %s, %s)
                ON CONFLICT (member_id, division_id) DO UPDATE SET
                  vote = EXCLUDED.vote
            ''', (member_pk_id, div_pk_id, vote_value))

            total += 1

        conn.commit()
        cursor.close()

    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM member_votes')
    vote_count = cursor.fetchone()[0]
    cursor.close()

    log_result('Member votes', vote_count)

def main():
    global conn

    try:
        conn = psycopg2.connect(DATABASE_URL)
        log_step("Connected to PostgreSQL")

        create_tables()
        fetch_members()
        fetch_bills()
        fetch_divisions()
        fetch_votes()

        log_step("Population complete!")
        print("\n  Next steps:")
        print("    psql $DATABASE_URL")
        print("    SELECT * FROM members LIMIT 5;")
        print("    SELECT m.full_name, COUNT(*) FROM member_votes mv")
        print("      JOIN members m ON m.id = mv.member_id")
        print("      GROUP BY m.full_name ORDER BY COUNT DESC LIMIT 10;")

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    main()
