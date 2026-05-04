from flask import Flask, jsonify, request
import psycopg2
import psycopg2.extras
import requests
from anthropic import Anthropic
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder='.', static_url_path='')

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://whoismytd:whoismytd@localhost:5432/whoismytd')
OIREACHTAS_API = 'https://api.oireachtas.ie/v1'
DAIL_34_START = '2024-11-29'   # 34th Dáil election date
client = Anthropic()
summary_cache = {}


def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def get_html_file(filename):
    filepath = Path(__file__).parent / filename
    if filepath.exists():
        with open(filepath, 'r') as f:
            return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}
    return 'Not found', 404


@app.route('/')
def index():
    return get_html_file('index.html')

@app.route('/<filename>.html')
def serve_html(filename):
    return get_html_file(f'{filename}.html')


@app.route('/api/tds', methods=['GET'])
def get_tds():
    """All 34th Dáil members grouped by constituency, served from DB."""
    try:
        conn = get_db()
        cur = conn.cursor()

        cur.execute('''
            SELECT
                m.pid,
                m.full_name,
                m.is_active,
                c.name AS constituency_name,
                p.name AS party_name
            FROM members m
            LEFT JOIN constituencies c ON m.constituency_id = c.id
            LEFT JOIN parties p ON m.party_id = p.id
            WHERE m.date_start = %s
            ORDER BY c.name, m.full_name
        ''', (DAIL_34_START,))

        rows = cur.fetchall()
        cur.close()
        conn.close()

        grouped = {}
        for row in rows:
            const = row['constituency_name'] or 'Unknown'
            if const not in grouped:
                grouped[const] = []
            grouped[const].append({
                'id': row['pid'],
                'member_id': row['pid'],
                'name': row['full_name'],
                'full_name': row['full_name'],
                'party_name': row['party_name'] or 'Independent',
                'house_name': 'Dáil Éireann',
                'constituency': const,
            })

        return jsonify({'constituencies': grouped})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/td/<pid>', methods=['GET'])
def get_td(pid):
    """Single TD profile + voting record from DB."""
    try:
        conn = get_db()
        cur = conn.cursor()

        cur.execute('''
            SELECT
                m.pid,
                m.full_name,
                m.first_name,
                m.last_name,
                m.gender,
                m.date_start,
                m.date_end,
                m.is_active,
                c.name AS constituency_name,
                p.name AS party_name
            FROM members m
            LEFT JOIN constituencies c ON m.constituency_id = c.id
            LEFT JOIN parties p ON m.party_id = p.id
            WHERE m.pid = %s
        ''', (pid,))

        member_row = cur.fetchone()
        if not member_row:
            cur.close()
            conn.close()
            return jsonify({'error': 'Member not found'}), 404

        member = {
            'pid': member_row['pid'],
            'name': member_row['full_name'],
            'full_name': member_row['full_name'],
            'first_name': member_row['first_name'],
            'last_name': member_row['last_name'],
            'gender': member_row['gender'],
            'party_name': member_row['party_name'] or 'Independent',
            'constituency': {'name': member_row['constituency_name'] or 'Unknown'},
            'is_active': member_row['is_active'],
        }

        cur.execute('''
            SELECT
                mv.vote,
                d.division_id,
                d.title AS bill_name,
                d.date,
                d.result
            FROM member_votes mv
            JOIN divisions d ON mv.division_id = d.id
            JOIN members m ON mv.member_id = m.id
            WHERE m.pid = %s
            ORDER BY d.date DESC
            LIMIT 50
        ''', (pid,))

        votes = []
        for v in cur.fetchall():
            votes.append({
                'vote': v['vote'],
                'division_id': v['division_id'],
                'bill_name': v['bill_name'],
                'date': v['date'].isoformat() if v['date'] else None,
                'result': v['result'],
            })

        cur.close()
        conn.close()

        return jsonify({'member': member, 'votes': votes})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/bills', methods=['GET'])
def get_bills():
    """Recent bills from DB, falling back to live API if DB is empty."""
    try:
        conn = get_db()
        cur = conn.cursor()

        cur.execute('''
            SELECT
                bill_id,
                title,
                description,
                bill_type,
                bill_status,
                date_introduced,
                uri
            FROM bills
            ORDER BY date_introduced DESC NULLS LAST
            LIMIT 50
        ''')

        rows = cur.fetchall()
        cur.close()
        conn.close()

        if rows:
            bills = [{
                'bill_id': r['bill_id'],
                'id': r['bill_id'],
                'title': r['title'],
                'description': r['description'],
                'bill_type': r['bill_type'],
                'bill_status': r['bill_status'],
                'date': r['date_introduced'].isoformat() if r['date_introduced'] else None,
                'uri': r['uri'],
            } for r in rows]
            return jsonify({'bills': bills})

        # Fallback to live API if DB is empty
        response = requests.get(f'{OIREACHTAS_API}/legislation', params={
            'house': 'dail', 'chamberNo': '34', 'limit': 50
        })
        response.raise_for_status()
        return jsonify({'bills': response.json().get('results', [])})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/bill/<bill_id>', methods=['GET'])
def get_bill(bill_id):
    """Bill detail + division breakdown from DB, falling back to live API."""
    try:
        conn = get_db()
        cur = conn.cursor()

        cur.execute('''
            SELECT bill_id, title, description, bill_type, bill_status, date_introduced, uri
            FROM bills WHERE bill_id = %s
        ''', (bill_id,))
        bill_row = cur.fetchone()

        cur.execute('''
            SELECT
                d.division_id,
                d.title,
                d.date,
                d.ta_count,
                d.nil_count,
                d.staon_count,
                d.result
            FROM divisions d
            JOIN bills b ON d.bill_id = b.id
            WHERE b.bill_id = %s
            ORDER BY d.date DESC
        ''', (bill_id,))
        division_rows = cur.fetchall()

        cur.close()
        conn.close()

        if bill_row:
            bill = {
                'bill_id': bill_row['bill_id'],
                'title': bill_row['title'],
                'description': bill_row['description'],
                'bill_type': bill_row['bill_type'],
                'bill_status': bill_row['bill_status'],
                'date': bill_row['date_introduced'].isoformat() if bill_row['date_introduced'] else None,
                'uri': bill_row['uri'],
            }
            divisions = [{
                'division_id': r['division_id'],
                'title': r['title'],
                'date': r['date'].isoformat() if r['date'] else None,
                'ta_count': r['ta_count'],
                'nil_count': r['nil_count'],
                'staon_count': r['staon_count'],
                'result': r['result'],
                'member_votes': [],
            } for r in division_rows]
            return jsonify({'bill': bill, 'divisions': divisions})

        # Fallback to live API
        bill_response = requests.get(f'{OIREACHTAS_API}/legislation/{bill_id}')
        bill_response.raise_for_status()
        bill = bill_response.json()['results'][0]
        divisions_response = requests.get(
            f'{OIREACHTAS_API}/legislation/{bill_id}/divisions', params={'limit': 10}
        )
        divisions = divisions_response.json().get('results', []) if divisions_response.ok else []
        return jsonify({'bill': bill, 'divisions': divisions})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/summary/<bill_id>', methods=['GET'])
def get_summary(bill_id):
    """AI plain-English summary for a bill, cached in memory."""
    if bill_id in summary_cache:
        return jsonify({'summary': summary_cache[bill_id]})

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT title, description FROM bills WHERE bill_id = %s', (bill_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()

        if row:
            bill_title = row['title']
            bill_description = row['description'] or ''
        else:
            # Fallback to live API
            resp = requests.get(f'{OIREACHTAS_API}/legislation/{bill_id}')
            resp.raise_for_status()
            bill = resp.json()['results'][0].get('bill', {})
            bill_title = bill.get('title', 'Bill')
            bill_description = bill.get('description', '')

        prompt = f"""Summarize this Irish Dáil bill in one concise paragraph (2-3 sentences). Be clear and direct. No jargon.

Bill: {bill_title}
Description: {bill_description}

Summary:"""

        message = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=200,
            messages=[{'role': 'user', 'content': prompt}]
        )

        summary = message.content[0].text.strip()
        summary_cache[bill_id] = summary
        return jsonify({'summary': summary})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/division/<division_id>', methods=['GET'])
def get_division(division_id):
    """Division detail with all member votes from DB."""
    try:
        conn = get_db()
        cur = conn.cursor()

        cur.execute('''
            SELECT d.division_id, d.title, d.date, d.ta_count, d.nil_count, d.staon_count, d.result,
                   b.title AS bill_title, b.bill_id
            FROM divisions d
            LEFT JOIN bills b ON d.bill_id = b.id
            WHERE d.division_id = %s
        ''', (division_id,))
        div_row = cur.fetchone()

        if not div_row:
            cur.close()
            conn.close()
            return jsonify({'error': 'Division not found'}), 404

        cur.execute('''
            SELECT m.pid, m.full_name, mv.vote, p.name AS party_name
            FROM member_votes mv
            JOIN members m ON mv.member_id = m.id
            LEFT JOIN parties p ON m.party_id = p.id
            WHERE mv.division_id = (SELECT id FROM divisions WHERE division_id = %s)
            ORDER BY mv.vote, m.full_name
        ''', (division_id,))
        vote_rows = cur.fetchall()

        cur.close()
        conn.close()

        division = {
            'division_id': div_row['division_id'],
            'title': div_row['title'],
            'date': div_row['date'].isoformat() if div_row['date'] else None,
            'ta_count': div_row['ta_count'],
            'nil_count': div_row['nil_count'],
            'staon_count': div_row['staon_count'],
            'result': div_row['result'],
            'bill_title': div_row['bill_title'],
            'bill_id': div_row['bill_id'],
        }
        votes = [{'pid': r['pid'], 'name': r['full_name'], 'vote': r['vote'], 'party': r['party_name']} for r in vote_rows]

        return jsonify({'division': division, 'votes': votes})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Live database stats for the landing page hero."""
    try:
        conn = get_db()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) AS count FROM members WHERE date_start = %s", (DAIL_34_START,))
        active_members = cur.fetchone()['count']

        cur.execute("SELECT COUNT(*) AS count FROM constituencies")
        total_constituencies = cur.fetchone()['count']

        cur.execute("SELECT COUNT(*) AS count FROM divisions")
        total_divisions = cur.fetchone()['count']

        cur.execute("SELECT COUNT(*) AS count FROM member_votes")
        total_votes = cur.fetchone()['count']

        cur.close()
        conn.close()

        return jsonify({
            'active_members': active_members,
            'constituencies': total_constituencies,
            'divisions': total_divisions,
            'votes': total_votes,
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)
