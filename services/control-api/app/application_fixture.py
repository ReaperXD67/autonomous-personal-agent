from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FORM = b"""<!doctype html><html><body><h1>Test application</h1>
<form method="post" enctype="multipart/form-data">
<label>First name <input name="first_name" required></label>
<label>Last name <input name="last_name" required></label>
<label>Email <input type="email" name="email" required></label>
<label>Phone <input name="phone"></label>
<label>Resume <input type="file" name="resume" accept=".pdf" required></label>
<label>Cover letter <textarea name="cover_letter" required></textarea></label>
<button type="submit">Submit application</button>
</form></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health/ready":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ready")
            return
        if self.path != "/apply":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(FORM)))
        self.end_headers()
        self.wfile.write(FORM)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/apply":
            self.send_error(404)
            return
        length = min(int(self.headers.get("content-length", "0")), 8 * 1024 * 1024)
        self.rfile.read(length)
        body = b"<!doctype html><html><body><h1>Application received</h1></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def main() -> None:
    ThreadingHTTPServer(("0.0.0.0", 8081), Handler).serve_forever()  # noqa: S104


if __name__ == "__main__":
    main()
