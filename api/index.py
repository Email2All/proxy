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
from flask import Flask, request, Response, jsonify
from flask_cors import CORS
import requests
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, supports_credentials=True)

def try_parse_request_json():
    """
    Try several ways to obtain structured JSON from the incoming request.
    Returns (parsed_json_or_None, raw_body_str, content_type)
    """
    content_type = request.headers.get("Content-Type", "")
    raw = None

    # 1) Standard attempt
    try:
        parsed = request.get_json(silent=True)
        if parsed is not None:
            return parsed, None, content_type
    except Exception as e:
        logger.debug("get_json failed: %s", e)

    # 2) Try request.data decode (in case content-type or encoding is odd)
    try:
        raw = request.get_data(cache=True).decode("utf-8", errors="replace")
        if raw:
            try:
                parsed = json.loads(raw)
                return parsed, None, content_type
            except Exception:
                # not JSON or nested JSON; return raw for debug
                return None, raw, content_type
    except Exception as e:
        logger.debug("request.data decode failed: %s", e)

    # 3) Try form fields (x-www-form-urlencoded or multipart)
    try:
        if request.form:
            # convert ImmutableMultiDict to normal dict
            form_dict = {k: request.form.get(k) for k in request.form.keys()}
            return form_dict, None, content_type
    except Exception as e:
        logger.debug("request.form parse failed: %s", e)

    # fallback
    return None, raw, content_type


@app.route('/proxy', methods=['POST'])
def proxy_post():
    """
    Forward POST to target URL and stream the response back to the client (SSE passthrough).
    Expects JSON like:
      { "url": "...", "headers": {...}, "body": "<string or object>" }
    This function will try to tolerate different input encodings and return a helpful error if it can't parse the request.
    """
    parsed, raw_body, content_type = try_parse_request_json()

    if parsed is None:
        # Provide helpful debug output (trim raw body for safety)
        snippet = (raw_body or "")[:2000]
        logger.warning("Unable to parse incoming request as JSON. Content-Type=%s, raw_snippet=%s", content_type, snippet[:500])
        return jsonify({
            "error": "Invalid JSON body",
            "note": "Proxy could not parse JSON from the request. See 'debug' for a short raw-body snippet.",
            "debug": {
                "content_type": content_type,
                "raw_snippet": snippet
            }
        }), 400

    # Now parsed should be a dict
    target_url = parsed.get('url')
    headers = parsed.get('headers') or {}
    body = parsed.get('body', "")

    if not target_url:
        return jsonify({"error": "url is required in JSON body"}), 400

    # If body is an object (dict/list), convert to a JSON string for forwarding
    if isinstance(body, (dict, list)):
        body = json.dumps(body)

    # Safe header adjustments
    headers.pop('Host', None)
    headers.setdefault('Accept', '*/*')
    if headers.get('Content-Type') is None and body:
        # if body looks like JSON set header
        try:
            json.loads(body)
            headers['Content-Type'] = 'application/json'
        except Exception:
            pass

    logger.info("Proxying POST to %s (content_type forwarded=%s)", target_url, headers.get('Content-Type'))
    try:
        # Use stream=True and iter_lines to preserve SSE boundaries
        with requests.post(target_url, headers=headers, data=body, stream=True, timeout=(5, None)) as resp:
            def generate():
                try:
                    for line in resp.iter_lines(decode_unicode=True):
                        if line is None:
                            continue
                        # yield each server-sent line with newline so client-side can split on \n
                        yield line + "\n"
                finally:
                    try:
                        resp.close()
                    except:
                        pass

            content_type_out = resp.headers.get('Content-Type', 'text/event-stream')
            return Response(generate(), content_type=content_type_out, status=resp.status_code)
    except requests.exceptions.RequestException as e:
        logger.exception("Error proxying request")
        return jsonify({"error": "upstream_request_failed", "detail": str(e)}), 502
    except Exception as e:
        logger.exception("Unexpected error")
        return jsonify({"error": "unexpected_error", "detail": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == '__main__':
    app.run(debug=True, threaded=True)
