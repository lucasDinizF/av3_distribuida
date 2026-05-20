import http.server
import socketserver
import urllib.request
import threading
from datetime import datetime

PORTA_BALANCEADOR = 3000

SERVIDORES_DESTINO = [
    {"host": "127.0.0.1", "porta": 3001, "nome": "Servidor Principal A", "cor": "#3498db", "requisicoes": 0},
    {"host": "127.0.0.1", "porta": 3002, "nome": "Servidor Reserva B", "cor": "#2ecc71", "requisicoes": 0}
]

indice_atual = 0
total_geral_requisicoes = 0
historico_logs = []
lock = threading.Lock()


class ServidorDestinoHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        porta_atual = self.server.server_address[1]
        servidor = next(s for s in SERVIDORES_DESTINO if s["porta"] == porta_atual)

        with lock:
            servidor["requisicoes"] += 1
            contagem_individual = servidor["requisicoes"]
            global total_geral_requisicoes
            total_geral_requisicoes += 1

            horario = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            log_msg = f"[{horario}] 🟢 {servidor['nome']} (Porta {porta_atual}) processou a requisição nº {contagem_individual}."
            historico_logs.insert(0, log_msg)

        conteudo_resposta = b"OK"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")

        self.send_header("Content-Length", str(len(conteudo_resposta)))
        self.end_headers()

        self.wfile.write(conteudo_resposta)


def iniciar_servidor_destino(info_servidor):
    handler = ServidorDestinoHandler
    with socketserver.TCPServer((info_servidor["host"], info_servidor["porta"]), handler) as httpd:
        print(f"-> {info_servidor['nome']} ativo em http://{info_servidor['host']}:{info_servidor['porta']}")
        httpd.serve_forever()

class LoadBalancerHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        global indice_atual

        if self.path == "/favicon.ico":
            self.send_response(404)
            self.end_headers()
            return

        with lock:
            servidor_escolhido = SERVIDORES_DESTINO[indice_atual]
            indice_atual = (indice_atual + 1) % len(SERVIDORES_DESTINO)

        horario_envio = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        url_destino = f"http://{servidor_escolhido['host']}:{servidor_escolhido['porta']}{self.path}"

        try:
            with urllib.request.urlopen(url_destino, timeout=2) as resposta_servidor:
                resposta_servidor.read()
        except Exception as e:
            with lock:
                historico_logs.insert(0,
                                      f"[{horario_envio}] 🔴 ERRO: Falha ao conectar com {servidor_escolhido['nome']}.")

        total = total_geral_requisicoes if total_geral_requisicoes > 0 else 1
        porcentagem_a = (SERVIDORES_DESTINO[0]["requisicoes"] / total) * 100
        porcentagem_b = (SERVIDORES_DESTINO[1]["requisicoes"] / total) * 100

        logs_html = "".join([f"<div class='log-line'>{log}</div>" for log in historico_logs[:12]])

        html_dashboard = f"""
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="UTF-8">
            <title>Painel de Controle - Balanceamento de Carga</title>
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #13131a; color: #fff; margin: 0; padding: 20px; }}
                .container {{ max-width: 900px; margin: 0 auto; }}
                header {{ text-align: center; margin-bottom: 25px; border-bottom: 2px solid #1f1f2e; padding-bottom: 20px; }}
                h1 {{ margin: 0; color: #f1c40f; font-size: 2.2rem; }}
                p {{ color: #8f8fbf; margin: 5px 0 15px 0; }}

                .btn-stress {{ background: #e74c3c; color: white; border: none; padding: 12px 24px; font-size: 1.1rem; font-weight: bold; border-radius: 8px; cursor: pointer; transition: background 0.2s; box-shadow: 0 4px 15px rgba(231, 76, 60, 0.3); }}
                .btn-stress:hover {{ background: #c0392b; }}

                .total-badge {{ background: #1f1f2e; padding: 8px 20px; border-radius: 20px; display: inline-block; margin-top: 15px; font-weight: bold; font-size: 1.2rem; border: 1px solid #2a2a40; }}

                .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 25px; }}
                .card {{ background: #1f1f2e; padding: 25px; border-radius: 12px; border-top: 8px solid #fff; border: 1px solid #2a2a40; }}
                .card.srv-a {{ border-top: 8px solid {SERVIDORES_DESTINO[0]['cor']}; }}
                .card.srv-b {{ border-top: 8px solid {SERVIDORES_DESTINO[1]['cor']}; }}
                .card h2 {{ margin: 0 0 15px 0; font-size: 1.4rem; color: #f5f5f5; }}

                .progress-bar {{ background: #111116; border-radius: 10px; height: 30px; width: 100%; margin-top: 15px; overflow: hidden; border: 1px solid #2a2a40; }}
                .progress-fill {{ height: 100%; transition: width 0.3s ease; display: flex; align-items: center; justify-content: flex-end; padding-right: 12px; font-weight: bold; font-size: 0.95rem; color: #fff; }}
                .fill-a {{ width: {porcentagem_a}%; background: {SERVIDORES_DESTINO[0]['cor']}; }}
                .fill-b {{ width: {porcentagem_b}%; background: {SERVIDORES_DESTINO[1]['cor']}; }}

                .console {{ background: #0c0c10; border-radius: 12px; padding: 20px; font-family: 'Consolas', monospace; border: 1px solid #1f1f2e; }}
                .console h3 {{ margin: 0 0 15px 0; color: #8f8fbf; border-bottom: 1px solid #1f1f2e; padding-bottom: 8px; }}
                .log-line {{ padding: 6px 0; border-bottom: 1px solid #111116; font-size: 0.95rem; color: #2ecc71; }}
                .log-line:first-child {{ font-weight: bold; color: #fff; background: rgba(255,255,255,0.05); }}
            </style>
            <script>
                // Função mágica que envia 20 requisições assíncronas em lote para o balanceador
                function dispararCarga() {{
                    let promessas = [];
                    for(let i=0; i<20; i++) {{
                        promessas.push(fetch('/simulacao-' + i));
                    }}
                    // Espera todas terminarem e recarrega a tela para computar os dados de uma vez
                    Promise.all(promessas).then(() => {{
                        window.location.reload();
                    }});
                }}
            </script>
        </head>
        <body>
            <div class="container">
                <header>
                    <h1>Dashboard de Arquitetura Distribuída</h1>
                    <p>Mecanismo de Proxy Reverso rodando em Algoritmo Round Robin</p>

                    <button class="btn-stress" onclick="dispararCarga()">🚀 Simular Enxurrada de Requisições (Stress Test)</button>
                    <br>
                    <div class="total-badge">📊 Volume Total Processado no Cluster: {total_geral_requisicoes}</div>
                </header>

                <div class="grid">
                    <div class="card srv-a">
                        <h2>🖥️ {SERVIDORES_DESTINO[0]['nome']}</h2>
                        <p style="color:#aaa; margin:0;">Endereço de Rede: <code>127.0.0.1:3001</code></p>
                        <p style="margin:10px 0 0 0;">Requisições Aceitas: <strong style="font-size:1.2rem; color:{SERVIDORES_DESTINO[0]['cor']};">{SERVIDORES_DESTINO[0]['requisicoes']}</strong></p>
                        <div class="progress-bar">
                            <div class="progress-fill fill-a">{porcentagem_a:.1f}%</div>
                        </div>
                    </div>

                    <div class="card srv-b">
                        <h2>🖥️ {SERVIDORES_DESTINO[1]['nome']}</h2>
                        <p style="color:#aaa; margin:0;">Endereço de Rede: <code>127.0.0.1:3002</code></p>
                        <p style="margin:10px 0 0 0;">Requisições Aceitas: <strong style="font-size:1.2rem; color:{SERVIDORES_DESTINO[1]['cor']};">{SERVIDORES_DESTINO[1]['requisicoes']}</strong></p>
                        <div class="progress-bar">
                            <div class="progress-fill fill-b">{porcentagem_b:.1f}%</div>
                        </div>
                    </div>
                </div>

                <div class="console">
                    <h3>📟 Histórico de Distribuição de Tráfego HTTP</h3>
                    {logs_html if total_geral_requisicoes > 0 else "<div style='color:#555'>Nenhuma requisição recebida ainda. Clique no botão acima para iniciar.</div>"}
                </div>
            </div>
        </body>
        </html>
        """

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html_dashboard.encode("utf-8"))


def iniciar_balanceador():
    with socketserver.TCPServer(("127.0.0.1", PORTA_BALANCEADOR), LoadBalancerHandler) as httpd:
        print("====================================================")
        print(f" BALANCEADOR ATIVO EM -> http://127.0.0.1:{PORTA_BALANCEADOR}")
        print("====================================================")
        httpd.serve_forever()


if __name__ == "__main__":
    for s in SERVIDORES_DESTINO:
        t = threading.Thread(target=iniciar_servidor_destino, args=(s,), daemon=True)
        t.start()

    iniciar_balanceador()