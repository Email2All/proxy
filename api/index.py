from flask import Flask, request, jsonify
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
        # Return the response from the target API
        return jsonify({
            "status_code": response.status_code,
            "response": response.json() if response.headers['Content-Type'] == 'application/json' else response.text
        })
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
