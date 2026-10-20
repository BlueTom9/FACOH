import json
import mimetypes
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen


class WebResponse:
    def __init__(self, body="", status=200, headers=None,
                 content_type=None):
        self.body = body
        self.status = int(status)
        self.headers = {} if headers is None else dict(headers)
        self.content_type = content_type

    @classmethod
    def json(cls, value, status=200, headers=None):
        return cls(value, status, headers, "application/json; charset=utf-8")

    @classmethod
    def text(cls, value, status=200, headers=None):
        return cls(value, status, headers, "text/plain; charset=utf-8")

    @classmethod
    def html(cls, value, status=200, headers=None):
        return cls(value, status, headers, "text/html; charset=utf-8")


def _compile_route(path):
    pieces = []
    names = []
    position = 0
    for match in re.finditer(r"<([A-Za-z_][A-Za-z0-9_]*)>", path):
        pieces.append(re.escape(path[position:match.start()]))
        name = match.group(1)
        if name in names:
            raise ValueError(f"duplicate route parameter '{name}'")
        names.append(name)
        pieces.append(f"(?P<{name}>[^/]+)")
        position = match.end()
    pieces.append(re.escape(path[position:]))
    return re.compile("^" + "".join(pieces) + "$"), names


class WebAPI:
    _methods = {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}  # noqa: RUF012
    def __init__(self, host="127.0.0.1", port=8000, cors_origin=None,
                 max_body=10 * 1024 * 1024):
        self.host = host
        self.port = int(port)
        self.cors_origin = cors_origin
        self.max_body = int(max_body)
        self._routes = []
        self._static_mounts = []
        self._lock = threading.RLock()
        self._callback_lock = threading.RLock()
        self._server = None
        self._server_thread = None

    @property
    def address(self):
        if self._server is None:
            return (self.host, self.port)
        return self._server.server_address[:2]

    @property
    def is_running(self):
        return self._server is not None

    def route(self, method, path, handler):
        method = str(method).upper()
        if method not in self._methods:
            raise ValueError(f"unsupported HTTP method '{method}'")
        if not path.startswith("/"):
            raise ValueError("route paths must start with '/'")
        if not callable(handler):
            raise TypeError("route handler must be callable")
        matcher, _ = _compile_route(path)
        with self._lock:
            self._routes.append((method, matcher, handler))
        return self

    def get(self, path, handler):
        return self.route("GET", path, handler)

    def post(self, path, handler):
        return self.route("POST", path, handler)

    def put(self, path, handler):
        return self.route("PUT", path, handler)

    def patch(self, path, handler):
        return self.route("PATCH", path, handler)

    def delete(self, path, handler):
        return self.route("DELETE", path, handler)

    def static(self, url_prefix, directory):
        if not url_prefix.startswith("/"):
            raise ValueError("static URL prefixes must start with '/'")
        prefix = url_prefix.rstrip("/") or "/"
        root = os.path.realpath(directory)
        if not os.path.isdir(root):
            raise NotADirectoryError(root)
        with self._lock:
            self._static_mounts.append((prefix, root))
        return self

    def _find_route(self, method, path):
        with self._lock:
            routes = tuple(self._routes)
        for route_method, matcher, callback in routes:
            if method == route_method or method == "HEAD" and route_method == "GET":
                match = matcher.match(path)
                if match:
                    return callback, match.groupdict()
        return None, {}

    def _find_static_file(self, path):
        with self._lock:
            mounts = tuple(self._static_mounts)
        for prefix, root in mounts:
            if path != prefix and not path.startswith(prefix + "/"):
                continue
            relative_path = path[len(prefix):].lstrip("/")
            target = os.path.realpath(os.path.join(root, relative_path))
            try:
                if os.path.commonpath((root, target)) != root:
                    continue
            except ValueError:
                continue
            if os.path.isfile(target):
                return target
        return None

    def _request_object(self, handler, body):
        parsed = urlsplit(handler.path)
        headers = {key.lower(): value for key,
                   value in handler.headers.items()}
        content_type = headers.get("content-type", "").split(";", 1)[0]
        body_text = body.decode("utf-8", errors="replace")
        body_json = None
        form = {}
        if body and content_type == "application/json":
            body_json = json.loads(body_text)
        elif body and content_type == "application/x-www-form-urlencoded":
            form = {
                key: values[-1] if len(values) == 1 else values
                for key, values in parse_qs(body_text).items()
            }
        query = {
            key: values[-1] if len(values) == 1 else values
            for key, values in parse_qs(parsed.query).items()
        }
        return {
            "method": handler.command,
            "path": parsed.path,
            "query": query,
            "params": {},
            "headers": headers,
            "body": body_text,
            "json": body_json,
            "form": form,
            "client": handler.client_address
        }

    @staticmethod
    def _response(value):
        if isinstance(value, WebResponse):
            response = value
        elif isinstance(value, tuple) and len(value) == 2:
            response = WebResponse(value[1], value[0])
        elif isinstance(value, bytes):
            response = WebResponse(
                value, content_type="application/octet-stream")
        elif isinstance(value, str):
            response = WebResponse.text(value)
        else:
            response = WebResponse.json(value)

        if isinstance(response.body, bytes):
            body = response.body
        elif response.content_type and "json" in response.content_type:
            body = json.dumps(
                response.body, ensure_ascii=False).encode("utf-8")
        else:
            body = str(response.body).encode("utf-8")
        return response, body

    def _handler_class(self):
        api = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, response_value):
                response, body = api._response(response_value)
                self.send_response(response.status)
                content_type = response.content_type
                if content_type is None:
                    content_type = "text/plain; charset=utf-8"
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                if api.cors_origin:
                    self.send_header(
                        "Access-Control-Allow-Origin", api.cors_origin)
                    self.send_header(
                        "Access-Control-Allow-Headers",
                        "Content-Type, Authorization"
                    )
                    self.send_header(
                        "Access-Control-Allow-Methods",
                        "GET, POST, PUT, PATCH, DELETE, OPTIONS"
                    )
                for name, value in response.headers.items():
                    self.send_header(name, str(value))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)

            def _handle(self):
                if self.command == "OPTIONS":
                    self._send(WebResponse("", 204))
                    return
                try:
                    content_length = int(
                        self.headers.get("Content-Length", "0"))
                except ValueError:
                    self._send(WebResponse.json(
                        {"error": "invalid content length"}, 400))
                    return
                if content_length < 0 or content_length > api.max_body:
                    self._send(WebResponse.json(
                        {"error": "request body too large"}, 413))
                    return
                try:
                    body = self.rfile.read(
                        content_length) if content_length else b""
                    request = api._request_object(self, body)
                except (UnicodeError, json.JSONDecodeError) as error:
                    self._send(WebResponse.json({"error": str(error)}, 400))
                    return

                callback, parameters = api._find_route(
                    self.command,
                    urlsplit(self.path).path
                )
                if callback is not None:
                    request["params"] = parameters
                    try:
                        with api._callback_lock:
                            result = callback(request)
                    except Exception:  # noqa: BLE001
                        self._send(WebResponse.json(
                            {"error": "internal server error"}, 500))
                        return
                    self._send(result)
                    return

                static_file = api._find_static_file(urlsplit(self.path).path)
                if static_file:
                    content_type = mimetypes.guess_type(static_file)[0]
                    with open(static_file, "rb") as file:
                        data = file.read()
                    self._send(WebResponse(
                        data,
                        200,
                        content_type=content_type or "application/octet-stream"
                    ))
                    return

                self._send(WebResponse.json({"error": "not found"}, 404))

            do_GET = _handle
            do_HEAD = _handle
            do_POST = _handle
            do_PUT = _handle
            do_PATCH = _handle
            do_DELETE = _handle
            do_OPTIONS = _handle

            def log_message(self, format_string, *args):
                return

        return Handler

    def start(self, threaded=True):
        if self._server is not None:
            raise RuntimeError("web server is already running")
        server_type = ThreadingHTTPServer if threaded else HTTPServer
        self._server = server_type(
            (self.host, self.port),
            self._handler_class()
        )
        if threaded:
            self._server_thread = threading.Thread(
                target=self._server.serve_forever,
                daemon=True
            )
            self._server_thread.start()
        else:
            self._server_thread = None
            self._server.serve_forever()
        return self.address

    def run(self):
        return self.start(threaded=False)

    def stop(self):
        server = self._server
        if server is None:
            return False
        self._server = None
        server.shutdown()
        server.server_close()
        thread = self._server_thread
        self._server_thread = None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)
        return True

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()


def http_request(method, url, data=None, headers=None, timeout=10):
    request_headers = {} if headers is None else dict(headers)
    body = None
    if data is not None:
        if isinstance(data, bytes):
            body = data
        elif isinstance(data, str):
            body = data.encode("utf-8")
        else:
            body = json.dumps(data).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
    request = Request(
        url,
        data=body,
        headers=request_headers,
        method=str(method).upper()
    )
    try:
        response = urlopen(request, timeout=timeout)
    except HTTPError as error:
        response = error
    except URLError as error:
        raise ConnectionError(str(error.reason)) from error
    with response:
        response_body = response.read()
        content_type = response.headers.get("Content-Type", "")
        if "json" in content_type:
            try:
                decoded_body = json.loads(response_body.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                decoded_body = response_body.decode("utf-8", errors="replace")
        else:
            decoded_body = response_body.decode("utf-8", errors="replace")
        return {
            "status": response.status,
            "headers": dict(response.headers.items()),
            "body": decoded_body
        }


def json_response(value, status=200, headers=None):
    return WebResponse.json(value, status, headers)


def text_response(value, status=200, headers=None):
    return WebResponse.text(value, status, headers)


def html_response(value, status=200, headers=None):
    return WebResponse.html(value, status, headers)


FUNCTIONS = {
    "open_api": WebAPI,
    "http_request": http_request,
    "json_response": json_response,
    "text_response": text_response,
    "html_response": html_response
}

OBJECTS = {
    "WebAPI": WebAPI,
    "WebResponse": WebResponse
}
