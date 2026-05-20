import json, time, threading, os
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from urllib.parse import urlparse

INITIAL_ITEMS = {
    "6901234567890": {"name": "Perno M8×20mm",            "unit": "EA",  "stock": 500, "location": "A-01-01", "min": 100},
    "6901234567891": {"name": "Rodamiento SKF 6205",       "unit": "EA",  "stock": 100, "location": "B-02-03", "min": 20},
    "6901234567892": {"name": "Sello O-Ring Φ50mm",        "unit": "EA",  "stock": 0,   "location": "A-03-02", "min": 50},
    "6901234567893": {"name": "Aceite Hidráulico 46# 20L", "unit": "brl", "stock": 30,  "location": "C-01-05", "min": 5},
    "6901234567894": {"name": "Malla Filtrante 200#",      "unit": "ud",  "stock": 80,  "location": "A-02-04", "min": 30},
    "6901234567895": {"name": "Correa B-1500",             "unit": "ud",  "stock": 15,  "location": "D-01-02", "min": 5},
    "6901234567896": {"name": "Relé 24V DC",               "unit": "EA",  "stock": 45,  "location": "E-03-01", "min": 10},
    "6901234567897": {"name": "Tarjeta Control Motor V3",  "unit": "EA",  "stock": 8,   "location": "E-01-03", "min": 3},
}

lock = threading.Lock()
items = {k: dict(v) for k, v in INITIAL_ITEMS.items()}
movements = []
counters = {"GR": 1000, "GI": 2000}

def now_str(): return datetime.now().strftime("%d/%m %H:%M:%S")
def make_ref(t): counters[t] += 1; return f"{t}-{counters[t]}"

def cors(h):
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    h.send_header("Access-Control-Allow-Headers", "Content-Type")

def send_json(h, data, status=200):
    body = json.dumps(data, ensure_ascii=False).encode()
    h.send_response(status)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Length", len(body))
    cors(h); h.end_headers(); h.wfile.write(body)

def read_body(h):
    n = int(h.headers.get("Content-Length", 0))
    return json.loads(h.rfile.read(n)) if n else {}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass

    def do_OPTIONS(self):
        self.send_response(204); cors(self); self.end_headers()

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/":
            with open(os.path.join(os.path.dirname(__file__), "index.html"), "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(body))
            cors(self); self.end_headers(); self.wfile.write(body)
        elif p == "/api/inventory":
            with lock: data = [{"barcode": k, **v} for k, v in items.items()]
            send_json(self, sorted(data, key=lambda x: x["location"]))
        elif p.startswith("/api/item/"):
            bc = p.split("/")[-1]
            with lock: item = items.get(bc)
            if item: send_json(self, {"barcode": bc, **item})
            else: send_json(self, {"error": "Artículo no encontrado"}, 404)
        elif p == "/api/movements":
            with lock: data = list(reversed(movements[-50:]))
            send_json(self, data)
        else: send_json(self, {"error": "not found"}, 404)

    def do_POST(self):
        p = urlparse(self.path).path
        b = read_body(self)

        if p in ("/api/receive", "/api/issue"):
            bc  = b.get("barcode", "").strip()
            qty = int(b.get("qty", 0))
            if not bc or qty <= 0:
                return send_json(self, {"error": "Código y cantidad son obligatorios"}, 400)
            with lock:
                if bc not in items:
                    return send_json(self, {"error": f"Artículo desconocido: {bc}"}, 404)
                it = items[bc]
                if p == "/api/issue" and it["stock"] < qty:
                    return send_json(self, {"error": f"Stock insuficiente, disponible: {it['stock']} {it['unit']}", "stock": it["stock"]}, 400)
                it["stock"] += qty if p == "/api/receive" else -qty
                typ = "GR" if p == "/api/receive" else "GI"
                ref = make_ref(typ)
                mv  = {"ref": ref, "type": "Entrada" if typ=="GR" else "Salida",
                       "barcode": bc, "name": it["name"], "qty": qty,
                       "location": it["location"], "stock_after": it["stock"], "time": now_str()}
                movements.append(mv)
            print(f"[{mv['time']}] {mv['type']} {mv['name']} {'+'if typ=='GR' else '-'}{qty} → {mv['stock_after']}")
            send_json(self, {"ok": True, "ref": ref, "name": it["name"],
                             "location": it["location"], "stock_after": mv["stock_after"],
                             "low_stock": mv["stock_after"] < it["min"]})

        elif p == "/api/reset":
            with lock:
                items.clear()
                items.update({k: dict(v) for k, v in INITIAL_ITEMS.items()})
                movements.clear(); counters["GR"]=1000; counters["GI"]=2000
            send_json(self, {"ok": True})
        else:
            send_json(self, {"error": "not found"}, 404)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"EWR WMS Demo → puerto {port}")
    HTTPServer(("", port), Handler).serve_forever()
