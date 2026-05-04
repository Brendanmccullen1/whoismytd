from flask import Flask, jsonify, request
import requests
from anthropic import Anthropic
import os
from pathlib import Path

app = Flask(__name__, static_folder='.', static_url_path='')

OIREACHTAS_API = 'https://api.oireachtas.ie/v1'
client = Anthropic()
summary_cache = {}

def get_html_file(filename):
    """Serve HTML files from the same directory as server.py"""
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
    """Fetch all members from the 34th Dáil, grouped by constituency"""
    try:
        response = requests.get(f'{OIREACHTAS_API}/members', params={'limit': 500, 'house': 'dail', 'chamberNo': '34'})
        response.raise_for_status()
        data = response.json()

        results = data.get('results', [])
        grouped = {}

        for item in results:
            member = item.get('member', {})
            pId = member.get('pId', '')
            full_name = member.get('fullName', member.get('showAs', 'Unknown'))

            memberships = member.get('memberships', [])
            const_name = 'Unknown'
            party_name = 'Independent'

            for membership in memberships:
                mem = membership.get('membership', {})
                house = mem.get('house', {})
                if house.get('houseNo') == '34':
                    represents = mem.get('represents', [])
                    if represents:
                        const_name = represents[0].get('represent', {}).get('showAs', 'Unknown')
                    parties = mem.get('parties', [])
                    if parties:
                        party_name = parties[0].get('party', {}).get('showAs', 'Independent')
                    break

            if const_name not in grouped:
                grouped[const_name] = []

            grouped[const_name].append({
                'id': pId,
                'member_id': pId,
                'name': full_name,
                'full_name': full_name,
                'party_name': party_name,
                'house_name': 'Dáil Éireann',
                'constituency': const_name
            })

        return jsonify({'constituencies': grouped})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/td/<pid>', methods=['GET'])
def get_td(pid):
    """Fetch member detail + their recent votes"""
    try:
        member_response = requests.get(f'{OIREACHTAS_API}/members', params={'memberCode': pid})
        member_response.raise_for_status()
        member_data = member_response.json()

        if not member_data.get('results'):
            return jsonify({'error': 'Member not found'}), 404

        member_item = member_data['results'][0]
        member = member_item.get('member', {})

        votes_response = requests.get(f'{OIREACHTAS_API}/members/{pid}/divisions', params={'limit': 50})
        votes_data = votes_response.json()
        votes = votes_data.get('results', [])

        return jsonify({'member': member, 'votes': votes})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bills', methods=['GET'])
def get_bills():
    """Fetch recent bills"""
    try:
        response = requests.get(f'{OIREACHTAS_API}/legislation', params={'limit': 50, 'date_start': '2024-01-01'})
        response.raise_for_status()
        bills = response.json()['results']
        return jsonify({'bills': bills})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bill/<bill_id>', methods=['GET'])
def get_bill(bill_id):
    """Fetch bill detail + vote breakdown"""
    try:
        bill_response = requests.get(f'{OIREACHTAS_API}/legislation/{bill_id}')
        bill_response.raise_for_status()
        bill = bill_response.json()['results'][0]

        divisions_response = requests.get(f'{OIREACHTAS_API}/legislation/{bill_id}/divisions', params={'limit': 10})
        divisions_response.raise_for_status()
        divisions = divisions_response.json()['results']

        return jsonify({'bill': bill, 'divisions': divisions})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/summary/<bill_id>', methods=['GET'])
def get_summary(bill_id):
    """Generate AI summary for a bill"""
    if bill_id in summary_cache:
        return jsonify({'summary': summary_cache[bill_id]})

    try:
        bill_response = requests.get(f'{OIREACHTAS_API}/legislation/{bill_id}')
        bill_response.raise_for_status()
        bill = bill_response.json()['results'][0]

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
    """Fetch division (vote) detail with all member votes"""
    try:
        response = requests.get(f'{OIREACHTAS_API}/divisions/{division_id}')
        response.raise_for_status()
        division = response.json()['results'][0]

        votes_response = requests.get(f'{OIREACHTAS_API}/divisions/{division_id}/votes', params={'limit': 200})
        votes_response.raise_for_status()
        votes = votes_response.json()['results']

        return jsonify({'division': division, 'votes': votes})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
