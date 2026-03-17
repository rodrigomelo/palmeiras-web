import os
import json

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')


def read_json(filename):
    """Read data from local JSON file."""
    filepath = os.path.join(DATA_DIR, filename)
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception as e:
        return {'error': str(e), 'data': []}


def teams_matches(request):
    """GET /api/teams/1769/matches"""
    status = request.args.get('status', 'SCHEDULED')
    limit = request.args.get('limit', '10')
    
    if status == 'SCHEDULED':
        data = read_json('matches_scheduled.json')
    else:
        data = read_json('matches_finished.json')
    
    # Filter by limit if needed
    if 'matches' in data and limit:
        data['matches'] = data['matches'][:int(limit)]
    
    return data, 200


def competitions(request):
    """GET /api/competitions/BSA/standings"""
    data = read_json('standings.json')
    return data, 200


def news(request):
    """GET /api/news - reads from local news.json (fetched by cron)"""
    return read_json('news.json')


def handler(request):
    """Main Vercel handler."""
    path = request.path
    
    if '/teams/' in path and '/matches' in path:
        return teams_matches(request)
    elif '/competitions/' in path and '/standings' in path:
        return competitions(request)
    elif path == '/api/news':
        return news(request)
    
    return {'error': 'Not found'}, 404
