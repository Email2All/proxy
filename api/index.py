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

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

@app.route('/', methods=['POST', 'GET'])
def proxy():
    if request.method == 'GET':
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

    elif request.method == 'POST':
        data = request.json
        url = data.get('url')
        headers = data.get('headers')
        
        if not url or not headers:
            return jsonify({"error": "URL and headers are required"}), 400
        
        try:
            response = requests.get(url, headers=headers)
            
            return jsonify({
                "status_code": response.status_code,
                "response": response.json() if response.headers.get('Content-Type', '').startswith('application/json') else response.text
            })
        except requests.exceptions.RequestException as e:
            return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
