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
logger = logging.getLogger("sse-proxy")

app = Flask(__name__)
# allow all origins (adjust in production)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# Hop-by-hop headers that should not be forwarded per RFC 2616
HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host"
}

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/proxy", methods=["POST"])
def proxy():
    """
    Expects JSON body like:
    {
      "url": "https://api.gpt-oss.com/chatkit",
      "method": "POST",            # optional, default POST
      "headers": {"Content-Type":"application/json", "Authorization":"..."},
      "body": {...}                # dict or string
    }
    Streams upstream response back to the client (preserving SSE/event-stream).
    """
    try:
        payload = request.get_json(force=True)
    except Exception as e:
        logger.exception("Invalid JSON")
        return jsonify({"error": "invalid_json", "detail": str(e)}), 400

    target_url = payload.get("url")
    if not target_url:
        return jsonify({"error": "url_required"}), 400

    method = (payload.get("method") or "POST").upper()
    headers = dict(payload.get("headers") or {})
    body = payload.get("body", None)

    # Merge client Authorization header if present (client may pass via real headers)
    # Give explicit headers in JSON precedence over actual incoming request headers
    client_auth = request.headers.get("Authorization")
    if client_auth and "Authorization" not in headers:
        headers["Authorization"] = client_auth

    # Remove hop-by-hop headers from forwarded headers
    for h in list(headers.keys()):
        if h.lower() in HOP_BY_HOP:
            headers.pop(h, None)

    # Ensure Accept is permissive so event-stream works
    headers.setdefault("Accept", "*/*")

    # If body is a dict/list, convert to JSON string (and set content-type if not set)
    data = None
    json_body = None
    if body is not None:
        if isinstance(body, (dict, list)):
            json_body = body
            headers.setdefault("Content-Type", "application/json")
        else:
            # body is probably a string already (e.g. pre-serialized JSON)
            data = body

    logger.info("Proxying %s %s", method, target_url)
    logger.debug("Forward headers: %s", headers)

    try:
        # Use requests to open a streaming connection to upstream.
        # For SSE/event-stream we must stream=True and iterate over lines/chunks.
        request_args = {
            "url": target_url,
            "headers": headers,
            "stream": True,
            # no connect/read timeout overall (connect timeout short, read none)
            "timeout": (10, None),
        }
        if method == "POST":
            if json_body is not None:
                request_args["json"] = json_body
            else:
                request_args["data"] = data
            r = requests.post(**request_args)
        elif method == "GET":
            r = requests.get(**request_args)
        elif method == "PUT":
            if json_body is not None:
                request_args["json"] = json_body
            else:
                request_args["data"] = data
            r = requests.put(**request_args)
        else:
            # fallback to generic request
            request_args["data"] = data
            r = requests.request(method, **request_args)

    except requests.exceptions.RequestException as e:
        logger.exception("Upstream connection failed")
        return jsonify({"error": "upstream_connection_failed", "detail": str(e)}), 502

    # Decide content-type for the response back to client
    upstream_ct = r.headers.get("Content-Type", "")
    if "text/event-stream" in upstream_ct:
        content_type = "text/event-stream"
    else:
        # preserve whatever upstream gave, fallback to stream type
        content_type = upstream_ct or "application/octet-stream"

    # Remove hop-by-hop headers from upstream response headers we might forward
    response_headers = {}
    for k, v in r.headers.items():
        if k.lower() not in HOP_BY_HOP:
            response_headers[k] = v

    # Ensure SSE-friendly headers
    response_headers.setdefault("Cache-Control", "no-cache, no-transform")
    response_headers.setdefault("Connection", "keep-alive")

    def generate():
        try:
            # Iterate over upstream lines. This works well for SSE.
            # r.iter_lines will wait for newline-separated chunks.
            for line in r.iter_lines(decode_unicode=True):
                # Note: iter_lines may yield empty strings on keep-alive; forward them to keep connection alive.
                if line is None:
                    continue
                # If upstream already sends SSE formatted lines (data: ...), forward as-is.
                # Add a single newline to preserve event boundaries.
                yield line + "\n"
        except GeneratorExit:
            # client disconnected; close upstream connection
            logger.info("Client disconnected, closing upstream stream")
            try:
                r.close()
            except Exception:
                pass
            raise
        except Exception as e:
            logger.exception("Error while streaming from upstream")
            # Optionally yield an error message for the client
            yield f"event: proxy_error\ndata: {json.dumps({'error': str(e)})}\n\n"
        finally:
            try:
                r.close()
            except Exception:
                pass

    # Return streaming Response with upstream status code & headers
    return Response(generate(), status=r.status_code, mimetype=content_type, headers=response_headers)

if __name__ == "__main__":
    # In dev: threaded=True to allow concurrent streaming connections
    app.run(debug=True, threaded=True)
