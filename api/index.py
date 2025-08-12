"""from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)  

@app.route('/', methods=['POST'])
def proxy():
    data = request.json
    url = data.get('url')
    headers = data.get('headers')
    
    if not url or not headers:
        return jsonify({"error": "URL and headers are required"}), 400
    
    try:
        response = requests.get(url, headers=headers)
        return jsonify({
            "status_code": response.status_code,
            "response": response.json() if response.headers['Content-Type'] == 'application/json' else response.text
        })
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
"""

# server.py
# server.py
# server_verbose.py
from flask import Flask, request, Response, jsonify
from flask_cors import CORS
import requests, json, logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("proxy")

app = Flask(__name__)
CORS(app, supports_credentials=True)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"}), 200

@app.route('/proxy', methods=['POST'])
def proxy():
    # Log incoming headers
    logger.info("Incoming request headers: %s", dict(request.headers))

    # Read raw data once and log snippet
    raw = request.get_data(cache=True)
    raw_snippet = raw[:4096].decode('utf-8', errors='replace')
    logger.info("Incoming raw body snippet (first 4KB):\n%s", raw_snippet)

    # attempt to parse JSON
    try:
        parsed = json.loads(raw.decode('utf-8'))
    except Exception as e:
        logger.warning("Failed to parse JSON: %s", e)
        return jsonify({"error": "Invalid JSON body", "debug_raw_snippet": raw_snippet}), 400

    target_url = parsed.get('url')
    headers = parsed.get('headers') or {}
    body = parsed.get('body', "")

    if not target_url:
        return jsonify({"error": "url is required"}), 400

    if isinstance(body, (dict, list)):
        body = json.dumps(body)

    # Remove hop-by-hop headers
    headers.pop('Host', None)
    headers.setdefault('Accept', '*/*')

    logger.info("Proxying to %s with headers: %s", target_url, headers)
    try:
        with requests.post(target_url, headers=headers, data=body, stream=True, timeout=(5, None)) as r:
            def gen():
                for line in r.iter_lines(decode_unicode=True):
                    if line is None:
                        continue
                    yield line + "\n"
            content_type = r.headers.get('Content-Type', 'text/event-stream')
            return Response(gen(), content_type=content_type, status=r.status_code)
    except Exception as e:
        logger.exception("Upstream error")
        return jsonify({"error": "upstream_failed", "detail": str(e)}), 502

if __name__ == '__main__':
    app.run(debug=True, threaded=True)

