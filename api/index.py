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

from flask import Flask, request, Response, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

@app.route('/proxy', methods=['POST'])
def proxy_post():
    """
    This endpoint forwards POST requests and supports streaming (SSE).
    """
    data = request.json
    target_url = data.get('url')
    headers = data.get('headers', {})
    body = data.get('body', "")

    if not target_url:
        return jsonify({"error": "URL is required"}), 400

    try:
        # Stream the POST request to the target API
        with requests.post(target_url, headers=headers, data=body, stream=True) as r:
            def generate():
                for chunk in r.iter_content(chunk_size=None):
                    if chunk:
                        yield chunk
            return Response(generate(), content_type=r.headers.get('Content-Type'))
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

@app.route('/proxy-get', methods=['GET'])
def proxy_get():
    """
    Optional GET proxy for debugging.
    """
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "URL is required"}), 400
    try:
        response = requests.get(url)
        return jsonify({
            "status_code": response.status_code,
            "response": response.json() if response.headers.get('Content-Type', '').startswith('application/json') else response.text
        })
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
