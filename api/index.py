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
from flask import Flask, request, Response, jsonify
from flask_cors import CORS
import requests
import json
import logging

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
# Allow any origin for easy testing; tighten this in production
CORS(app)

@app.route('/proxy', methods=['POST'])
def proxy_post():
    """
    Forward POST to target URL and stream the response back to the client (SSE passthrough).
    Expect JSON body: { "url": "...", "headers": {...}, "body": "<string or object>" }
    """
    try:
        data = request.get_json(force=True)
    except Exception as e:
        return jsonify({"error": "Invalid JSON body", "exception": str(e)}), 400

    target_url = data.get('url')
    headers = data.get('headers', {}) or {}
    body = data.get('body', "")

    if not target_url:
        return jsonify({"error": "url is required"}), 400

    # If body is an object, convert to string
    if isinstance(body, (dict, list)):
        body = json.dumps(body)

    # Remove or override any hop-by-hop headers that might break forwarding
    headers.pop('Host', None)
    headers.setdefault('Accept', '*/*')
    # If client didn't set Content-Type but body is JSON, try to set it
    if headers.get('Content-Type') is None and body:
        # leave it to caller, but safe to default to application/json if body looks like json
        try:
            json.loads(body)
            headers['Content-Type'] = 'application/json'
        except Exception:
            pass

    logging.info("Proxying POST -> %s", target_url)

    try:
        # stream=True so we can iterate lines as they arrive
        with requests.post(target_url, headers=headers, data=body, stream=True, timeout=(5, None)) as resp:
            # Use resp.iter_lines to maintain SSE line boundaries
            def generate():
                try:
                    for line in resp.iter_lines(decode_unicode=True):
                        # iter_lines returns '' for keepalive newlines, None sometimes; skip those
                        if line is None:
                            continue
                        # Yield the line plus newline so browser's reader receives boundaries
                        yield line + "\n"
                finally:
                    try:
                        resp.close()
                    except:
                        pass

            # Use upstream content-type if present, otherwise default to text/event-stream
            content_type = resp.headers.get('Content-Type', 'text/event-stream')
            # Return the stream with the status code of the upstream (usually 200)
            return Response(generate(), content_type=content_type, status=resp.status_code)
    except requests.exceptions.RequestException as e:
        logging.exception("Error proxying request")
        return jsonify({"error": str(e)}), 502
    except Exception as e:
        logging.exception("Unexpected error")
        return jsonify({"error": str(e)}), 500


@app.route('/proxy-get', methods=['GET'])
def proxy_get():
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "url query param is required"}), 400
    try:
        r = requests.get(url)
        return jsonify({
            "status_code": r.status_code,
            "response": r.json() if r.headers.get('Content-Type', '').startswith('application/json') else r.text
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    # For production use a WSGI server (gunicorn). This is fine for quick testing.
    app.run(debug=True, threaded=True)

