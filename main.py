import sys
import os
import json
import asyncio
import aiohttp
import qasync
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl, QTimer, Qt, QPoint

SSE_URL = "http://127.0.0.1:8000/sse"  # Endpoint SSE de tu backend

def resource_path(relative_path):
    """Devuelve la ruta absoluta de un archivo, incluso dentro de un exe PyInstaller."""
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class DragOverlay(QWidget):
    """Widget transparente para capturar el mouse y arrastrar la ventana."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setMouseTracking(True)
        self.dragging = False
        self.drag_position = QPoint()
        self.resize(parent.size())
        self.show()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPos() - self.parent().frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() & Qt.LeftButton:
            self.parent().move(event.globalPos() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.dragging = False
        event.accept()


class PatenteApp(QMainWindow):
    def __init__(self, ancho=384, alto=192):
        super().__init__()
        self.setWindowTitle("Patentes Argentina")
        self.resize(ancho, alto)

        # Quitar barra de título y bordes
        self.setWindowFlags(Qt.FramelessWindowHint)

        # WebEngine con HTML local
        self.browser = QWebEngineView(self)
        html_path = resource_path("patentes.html")
        self.browser.setUrl(QUrl.fromLocalFile(html_path))
        self.setCentralWidget(self.browser)

        # Overlay para arrastrar
        self.overlay = DragOverlay(self)
        self.overlay.raise_()  # asegurar que quede encima

        # Centrar ventana
        self.center_on_screen()

        # Control para saber si JS está listo
        self.js_ready = False
        self.pending_queue = []

        # Verificar si queuePlate está disponible
        self.browser.loadFinished.connect(self.check_js_ready)

        # Lanzar asyncio loop en segundo plano para SSE
        asyncio.get_event_loop().create_task(self.sse_listener())

    def center_on_screen(self):
        screen = QApplication.primaryScreen().availableGeometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    # -----------------
    # JS queuePlate
    # -----------------
    def check_js_ready(self):
        """Verifica si queuePlate está definida en el JS."""
        def callback(result):
            if result:
                self.js_ready = True
                for patente in self.pending_queue:
                    self.inject_plate(patente)
                self.pending_queue.clear()
            else:
                QTimer.singleShot(100, self.check_js_ready)

        self.browser.page().runJavaScript(
            "typeof window.queuePlate === 'function';", callback
        )

    def inject_plate(self, patente):
        """Inyecta la patente en el JS cuando esté listo."""
        def run():
            js = f'queuePlate({json.dumps(patente)})'
            self.browser.page().runJavaScript(js)
            print("📤 Patente enviada a HTML:", patente)

        if self.js_ready:
            QTimer.singleShot(0, run)
        else:
            self.pending_queue.append(patente)

    # -----------------
    # SSE listener con aiohttp
    # -----------------
    async def sse_listener(self):
        headers = {'Accept': 'text/event-stream'}
        while True:
            try:
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.get(SSE_URL, timeout=None) as resp:
                        if resp.status == 200:
                            print("🔌 Conectado al stream SSE.")
                            async for line_bytes in resp.content:
                                line = line_bytes.decode('utf-8').strip()
                                if line.startswith('data:'):
                                    data_json = line[len('data:'):].strip()
                                    if data_json:
                                        try:
                                            data = json.loads(data_json)
                                            patente = data.get("placa", "")
                                            if patente:
                                                print("📥 Patente recibida de SSE:", patente)
                                                self.inject_plate(patente)
                                        except json.JSONDecodeError:
                                            print(f"⚠️ Error JSON: {data_json}")
                        else:
                            print(f"⚠️ Error SSE: Status {resp.status}, reconectando en 5s...")

            except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
                print(f"🔌 Error de conexión, reintentando en 5s: {e}")
            except Exception as e:
                print(f"⚠️ Error inesperado en SSE: {e}")

            await asyncio.sleep(5)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    ventana = PatenteApp(ancho=1024, alto=512)
    ventana.show()

    with loop:
        loop.run_forever()
