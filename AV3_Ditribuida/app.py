import http.server
import socketserver
import urllib.request
import threading
import random
from datetime import datetime

PORTA_BALANCEADOR = 3100

SERVIDORES_DESTINO = [
    {"host": "127.0.0.1", "porta": 3101, "nome": "Servidor Principal A", "cor": "#3498db", "requisicoes": 0,
     "ativo": True},
    {"host": "127.0.0.1", "porta": 3102, "nome": "Servidor Reserva B", "cor": "#2ecc71", "requisicoes": 0,
     "ativo": True}
]

total_geral_requisicoes = 0
historico_logs = []
lock = threading.Lock()


class ServidorDestinoHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        porta_atual = self.server.server_address[1]
        servidor = next((s for s in SERVIDORES_DESTINO if s["porta"] == porta_atual), None)

        if servidor and not servidor["ativo"]:
            self.send_response(503)
            self.end_headers()
            return

        with lock:
            if servidor:
                servidor["requisicoes"] += 1
                contagem = servidor["requisicoes"]
            global total_geral_requisicoes
            total_geral_requisicoes += 1
            horario = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            historico_logs.insert(0,
                                  f"[{horario}] 🟢 {servidor['nome']} (Porta {porta_atual}) processou a requisição nº {contagem}.")

        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")


def iniciar_servidor_destino(info):
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((info["host"], info["porta"]), ServidorDestinoHandler) as httpd:
        print(f" {info['nome']} ativo em http://{info['host']}:{info['porta']}")
        httpd.serve_forever()


class LoadBalancerHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/favicon.ico":
            self.send_response(404)
            self.end_headers()
            return

        if self.path.startswith("/alternar/"):
            porta_alvo = int(self.path.split("/")[-1])
            for s in SERVIDORES_DESTINO:
                if s["porta"] == porta_alvo:
                    s["ativo"] = not s["ativo"]
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
            return

        if self.path.startswith("/simulacao-"):
            horario_envio = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            sucesso = False

            with lock:
                servidores_ativos = [s for s in SERVIDORES_DESTINO if s["ativo"]]

            if len(servidores_ativos) == 2:
                srv_a, srv_b = servidores_ativos[0], servidores_ativos[1]
                req_a, req_b = srv_a["requisicoes"], srv_b["requisicoes"]
                total_reqs = req_a + req_b

                if total_reqs == 0:
                    servidor_escolhido = random.choice(servidores_ativos)
                else:

                    peso_a = 1.0 - (req_a / total_reqs)
                    peso_b = 1.0 - (req_b / total_reqs)


                    servidor_escolhido = random.choices([srv_a, srv_b], weights=[peso_a, peso_b], k=1)[0]

            elif len(servidores_ativos) == 1:

                servidor_escolhido = servidores_ativos[0]
            else:
                servidor_escolhido = None

            if servidor_escolhido:
                try:
                    url_destino = f"http://{servidor_escolhido['host']}:{servidor_escolhido['porta']}{self.path}"
                    with urllib.request.urlopen(url_destino, timeout=0.5) as resp:
                        if resp.getcode() == 200:
                            sucesso = True
                except Exception:
                    with lock:
                        historico_logs.insert(0,
                                              f"[{horario_envio}] 🔴 ERRO: Falha ao conectar em {servidor_escolhido['nome']}.")
            else:
                with lock:
                    historico_logs.insert(0, f"[{horario_envio}] 🔴 FALHA: Todos os servidores estão OFFLINE!")

            if sucesso:
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"OK")
            else:
                self.send_response(502)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                msg_erro = "CORRUPTO: Nenhum servidor disponível no cluster!"
                self.wfile.write(msg_erro.encode("utf-8"))
            return

        # ROTA PRINCIPAL: DASHBOARD HTML
        total = total_geral_requisicoes if total_geral_requisicoes > 0 else 1
        porcentagem_a = (SERVIDORES_DESTINO[0]["requisicoes"] / total) * 100
        porcentagem_b = (SERVIDORES_DESTINO[1]["requisicoes"] / total) * 100

        logs_html = "".join(
            [f"<div style='padding:5px 0; border-bottom:1px solid #222;'>{log}</div>" for log in historico_logs[:12]])

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Load Balancer Dinâmico Proporcional</title>
            <style>
                body {{ font-family: sans-serif; background: #121214; color: #fff; padding: 20px; }}
                .container {{ max-width: 800px; margin: 0 auto; text-align: center; }}
                .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0; }}
                .card {{ background: #202024; padding: 20px; border-radius: 8px; border-top: 6px solid; text-align: left; }}
                .btn {{ background: #e74c3c; color: #fff; border: none; padding: 10px 20px; font-weight: bold; cursor: pointer; border-radius: 5px; }}
                .btn-toggle {{ background: #555; color: #fff; border: none; padding: 6px 12px; cursor: pointer; border-radius: 4px; }}
                .console {{ background: #0c0c0e; padding: 15px; text-align: left; font-family: monospace; border-radius: 6px; max-height: 250px; overflow-y: auto; }}
                .alert-danger {{ display: none; background: #5a1919; color: #ff9999; padding: 15px; border: 2px solid #e74c3c; border-radius: 6px; margin-bottom: 20px; font-weight: bold; font-size: 1.1rem; }}
            </style>
            <script>
                async function testar() {{
                    document.getElementById('erro-painel').style.display = 'none';
                    let falhou = false;

                    for(let i=0; i<20; i++) {{
                        try {{
                            let resposta = await fetch('/simulacao-' + i + '?t=' + Date.now());
                            if (resposta.status === 502) {{
                                falhou = true;
                            }}
                        }} catch (e) {{
                            falhou = true;
                        }}
                    }}

                    if (falhou) {{
                        document.getElementById('erro-painel').style.display = 'block';
                        setTimeout(() => {{ location.reload(); }}, 3000); 
                    }} else {{
                        location.reload();
                    }}
                }}
            </script>
        </head>
        <body>
            <div class="container">
                <h1>Balanceador de Carga HTTP</h1>
                <h3>Algoritmo: Balanceamento Proporcional por Compensação</h3>

                <div id="erro-painel" class="alert-danger">
                    🚨 ERRO 502: BAD GATEWAY!<br>
                    O sistema tentou escoar o tráfego, mas todos os servidores do cluster estão caídos!
                </div>

                <button class="btn" onclick="testar()">🚀 Simular 20 Requisições</button>
                <p>Volume Total: <strong>{total_geral_requisicoes}</strong></p>

                <div class="grid">
                    <div class="card" style="border-color: {SERVIDORES_DESTINO[0]['cor']}; opacity: {1 if SERVIDORES_DESTINO[0]['ativo'] else 0.4};">
                        <h3>{SERVIDORES_DESTINO[0]['nome']} ({'🟢 ON' if SERVIDORES_DESTINO[0]['ativo'] else '🔴 OFF'})</h3>
                        <p>Porta: 3101 | Requisições Processadas: <strong>{SERVIDORES_DESTINO[0]['requisicoes']}</strong> ({porcentagem_a:.1f}%)</p>
                        <button class="btn-toggle" onclick="location.href='/alternar/3101'">Derrubar / Ligar</button>
                    </div>
                    <div class="card" style="border-color: {SERVIDORES_DESTINO[1]['cor']}; opacity: {1 if SERVIDORES_DESTINO[1]['ativo'] else 0.4};">
                        <h3>{SERVIDORES_DESTINO[1]['nome']} ({'🟢 ON' if SERVIDORES_DESTINO[1]['ativo'] else '🔴 OFF'})</h3>
                        <p>Porta: 3102 | Requisições Processadas: <strong>{SERVIDORES_DESTINO[1]['requisicoes']}</strong> ({porcentagem_b:.1f}%)</p>
                        <button class="btn-toggle" onclick="location.href='/alternar/3102'">Derrubar / Ligar</button>
                    </div>
                </div>

                <div class="console">
                    <h4>📟 Logs do Cluster:</h4>
                    {logs_html if historico_logs else "Nenhum evento registrado ainda."}
                </div>
            </div>
        </body>
        </html>
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))


def iniciar():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORTA_BALANCEADOR), LoadBalancerHandler) as httpd:
        print(f" BALANCEADOR ONLINE EM: http://127.0.0.1:{PORTA_BALANCEADOR} ")
        httpd.serve_forever()


if __name__ == "__main__":
    for s in SERVIDORES_DESTINO:
        threading.Thread(target=iniciar_servidor_destino, args=(s,), daemon=True).start()
    iniciar()
