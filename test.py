import requests
import sseclient
import json

SSE_URL = "http://127.0.0.1:8000/sse"

# Crear la conexión SSE
response = requests.get(SSE_URL, stream=True)
client = sseclient.SSEClient(response)

# Iterar sobre los eventos
for event in client:
    try:
        data = json.loads(event.data)
        print("Patente:", data.get("placa"), "Hora:", data.get("hora"))
    except json.JSONDecodeError:
        print("Evento recibido pero no es JSON:", event.data)
