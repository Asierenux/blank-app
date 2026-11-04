"""Servidor HTTP local que imita POST /v1/messages en streaming (SSE) con respuestas guionizadas."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeAPI:
    def __init__(self, respuestas: list[str]):
        self.respuestas = list(respuestas)  # textos JSON que devolverá Claude, en orden
        self.peticiones: list[dict] = []
        self.cabeceras: list[dict] = []
        api = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["content-length"])))
                api.peticiones.append(body)
                api.cabeceras.append(dict(self.headers))
                texto = api.respuestas.pop(0)
                if isinstance(texto, int):  # simula un error HTTP de la API
                    cuerpo = json.dumps({"type": "error", "error": {"type": "api_error", "message": "fallo simulado"}}).encode()
                    self.send_response(texto)
                    self.send_header("content-type", "application/json")
                    self.send_header("content-length", str(len(cuerpo)))
                    self.end_headers()
                    self.wfile.write(cuerpo)
                    return
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.end_headers()
                ev = [
                    ("message_start", {"type": "message_start", "message": {
                        "id": f"msg_{len(api.peticiones)}", "type": "message", "role": "assistant", "model": body["model"],
                        "content": [], "stop_reason": None, "stop_sequence": None,
                        "usage": {"input_tokens": 10, "output_tokens": 0}}}),
                    ("content_block_start", {"type": "content_block_start", "index": 0,
                                             "content_block": {"type": "thinking", "thinking": "", "signature": ""}}),
                    ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                             "delta": {"type": "signature_delta", "signature": "sig123"}}),
                    ("content_block_stop", {"type": "content_block_stop", "index": 0}),
                    ("content_block_start", {"type": "content_block_start", "index": 1,
                                             "content_block": {"type": "text", "text": ""}}),
                ]
                for i in range(0, len(texto), 500):
                    ev.append(("content_block_delta", {"type": "content_block_delta", "index": 1,
                                                       "delta": {"type": "text_delta", "text": texto[i:i + 500]}}))
                ev += [
                    ("content_block_stop", {"type": "content_block_stop", "index": 1}),
                    ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                                       "usage": {"output_tokens": 50}}),
                    ("message_stop", {"type": "message_stop"}),
                ]
                for name, data in ev:
                    self.wfile.write(f"event: {name}\ndata: {json.dumps(data)}\n\n".encode())
                self.wfile.flush()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def client(self):
        import anthropic
        return anthropic.Anthropic(api_key="test", base_url=self.url, max_retries=0)

    def close(self):
        self.server.shutdown()
