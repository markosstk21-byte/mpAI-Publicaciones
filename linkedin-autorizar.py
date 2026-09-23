#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Autorización de LinkedIn. Se ejecuta A MANO en tu ordenador, no en GitHub.

Hace falta cada vez que caduca el token, que es cada 60 días. Los tokens de
refresco programáticos están reservados a socios aprobados, así que no hay
forma de automatizar esta parte: es la pieza manual del flujo y conviene
saberlo desde el principio en vez de descubrirlo el día que falle.

Qué hace:
  1. Abre el navegador en la pantalla de permisos de LinkedIn.
  2. Escucha en http://localhost:8765/callback para recoger el código.
  3. Lo cambia por un token.
  4. Pregunta a LinkedIn quién eres y saca tu identificador de persona.
  5. Te imprime los tres valores que hay que meter en los secretos de GitHub.

Uso:
    set LI_CLIENT_ID=xxxx
    set LI_CLIENT_SECRET=xxxx
    python linkedin-autorizar.py

En la aplicación de LinkedIn tiene que estar dada de alta exactamente esta
dirección de redirección:  http://localhost:8765/callback
"""

import http.server
import json
import os
import secrets
import socketserver
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from datetime import date, timedelta

PUERTO = 8765
REDIRECCION = f"http://localhost:{PUERTO}/callback"
AUTORIZAR = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN = "https://www.linkedin.com/oauth/v2/accessToken"
USUARIO = "https://api.linkedin.com/v2/userinfo"

# openid y profile solo se usan aquí, para averiguar tu identificador de persona.
# w_member_social es el que de verdad permite publicar.
PERMISOS = "openid profile w_member_social"

recibido = {}


class Recogedor(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        partes = urllib.parse.urlparse(self.path)
        if partes.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        consulta = urllib.parse.parse_qs(partes.query)
        recibido.update({k: v[0] for k, v in consulta.items()})
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            "<h2>Listo. Ya puedes cerrar esta pestaña y volver a la consola.</h2>"
            .encode("utf-8"))

    def log_message(self, *args):
        pass  # sin ruido en la consola


def main():
    cliente = os.environ.get("LI_CLIENT_ID", "").strip()
    secreto = os.environ.get("LI_CLIENT_SECRET", "").strip()
    if not cliente or not secreto:
        print("Faltan LI_CLIENT_ID o LI_CLIENT_SECRET en las variables de entorno.")
        sys.exit(1)

    estado = secrets.token_urlsafe(16)
    url = AUTORIZAR + "?" + urllib.parse.urlencode({
        "response_type": "code",
        "client_id": cliente,
        "redirect_uri": REDIRECCION,
        "state": estado,
        "scope": PERMISOS,
    })

    servidor = socketserver.TCPServer(("localhost", PUERTO), Recogedor)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()

    print("Abriendo el navegador para que autorices la aplicación...")
    print(f"Si no se abre solo, entra tú aquí:\n{url}\n")
    webbrowser.open(url)

    while "code" not in recibido and "error" not in recibido:
        pass
    servidor.shutdown()

    if "error" in recibido:
        print(f"LinkedIn devolvió un error: {recibido.get('error')} "
              f"— {recibido.get('error_description', '')}")
        sys.exit(1)
    if recibido.get("state") != estado:
        print("El parámetro de estado no coincide. Abortado por seguridad.")
        sys.exit(1)

    datos = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": recibido["code"],
        "redirect_uri": REDIRECCION,
        "client_id": cliente,
        "client_secret": secreto,
    }).encode()
    peticion = urllib.request.Request(TOKEN, data=datos, method="POST")
    peticion.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(peticion, timeout=60) as r:
        respuesta = json.loads(r.read().decode())

    token = respuesta["access_token"]
    segundos = int(respuesta.get("expires_in", 0))
    caduca = date.today() + timedelta(seconds=segundos)

    peticion = urllib.request.Request(USUARIO, method="GET")
    peticion.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(peticion, timeout=60) as r:
        yo = json.loads(r.read().decode())
    urn = f"urn:li:person:{yo['sub']}"

    print("\n" + "=" * 70)
    print("Autorizado. Mete estos tres valores en los secretos del repositorio:")
    print("=" * 70)
    print(f"LI_TOKEN          {token}")
    print(f"LI_PERSON_URN     {urn}")
    print(f"LI_TOKEN_EXPIRA   {caduca.isoformat()}")
    print("=" * 70)
    print(f"Nombre en LinkedIn: {yo.get('name', '(no lo dice)')}")
    print(f"El token dura {segundos // 86400} días. Apunta la fecha: {caduca}.")
    print("Cuando falten 10 días, el publicador empezará a avisarte en el registro,")
    print("y el aviso semanal te mandará un correo cuando queden menos de 7.")


if __name__ == "__main__":
    main()
