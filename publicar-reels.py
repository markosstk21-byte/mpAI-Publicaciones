#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Publicador de reels en Instagram para @mpai.technologies.

Hermano de publicar.py (carruseles), con el mismo criterio de seguridad, pero
para media_type=REELS: un único vídeo en vez de varias imágenes, y un tiempo de
procesado mayor porque Instagram tarda más en preparar un vídeo que una imagen.

Lee calendario-reels.json, mira qué toca hoy y publica el reel del día.

Uso:
    python publicar-reels.py --prueba     # no publica: enseña qué haría
    python publicar-reels.py              # publica de verdad (si PUBLICAR_REELS_DE_VERDAD=1)

Variables de entorno necesarias:
    IG_TOKEN                  token de acceso de larga duración de Meta (el mismo que carruseles)
    IG_USER_ID                identificador de la cuenta de Instagram (el mismo)
    BASE_URL                  dirección pública donde vive el repositorio (GitHub Pages)
    PUBLICAR_REELS_DE_VERDAD  "1" para publicar; cualquier otra cosa = modo revisión.
                               Interruptor PROPIO, separado de PUBLICAR_DE_VERDAD (carruseles):
                               activar uno no activa el otro.
    FECHA_FORZAR               opcional, "AAAA-MM-DD", igual que en publicar.py

La API no acepta archivos: se le pasa la URL pública del vídeo y ella la descarga.
"""

import json
import os
import sys
import time
import datetime
import urllib.request
import urllib.parse
import urllib.error

API_HOST = os.environ.get("IG_API_HOST", "https://graph.instagram.com")
API_VERSION = os.environ.get("IG_API_VERSION", "v23.0")

TIEMPO_ESPERA = 30
REINTENTOS = 3
ESPERA_BASE = 5
ESPERA_CONTENEDOR = 10
# Un vídeo tarda más que una imagen en procesarse. 10 minutos en vez de los 5 de
# los carruseles, mismo criterio: es el límite que recomienda Meta para no
# encadenar consultas indefinidamente.
MAX_ESPERA_CONTENEDOR = 600

RAIZ = os.path.dirname(os.path.abspath(__file__))
CALENDARIO = os.path.join(RAIZ, "calendario-reels.json")
REGISTRO = os.path.join(RAIZ, "registro-reels.json")


def log(msg):
    ahora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ahora}] {msg}", flush=True)


def error_y_salir(msg, codigo=1):
    log(f"ERROR: {msg}")
    sys.exit(codigo)


def peticion(metodo, ruta, parametros):
    url = f"{API_HOST}/{API_VERSION}/{ruta}"
    datos = urllib.parse.urlencode(parametros).encode()

    espera = ESPERA_BASE
    for intento in range(1, REINTENTOS + 1):
        try:
            req = urllib.request.Request(url, data=datos, method=metodo)
            with urllib.request.urlopen(req, timeout=TIEMPO_ESPERA) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            cuerpo = e.read().decode(errors="replace")
            temporal = e.code == 429 or e.code >= 500
            log(f"  respuesta {e.code} (intento {intento}/{REINTENTOS}): {cuerpo[:300]}")
            if not temporal:
                raise RuntimeError(f"error permanente {e.code}: {cuerpo[:300]}")
            if intento == REINTENTOS:
                raise RuntimeError(f"agotados los reintentos: {cuerpo[:300]}")
        except urllib.error.URLError as e:
            log(f"  red no disponible (intento {intento}/{REINTENTOS}): {e.reason}")
            if intento == REINTENTOS:
                raise RuntimeError(f"sin conexión con la API: {e.reason}")
        time.sleep(espera)
        espera *= 2
    raise RuntimeError("estado imposible en peticion()")


def cargar_json(ruta, por_defecto):
    if not os.path.exists(ruta):
        return por_defecto
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def guardar_json(ruta, datos):
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)


def crear_contenedor_reel(token, user_id, url_video, pie):
    r = peticion("POST", f"{user_id}/media", {
        "media_type": "REELS",
        "video_url": url_video,
        "caption": pie,
        "share_to_feed": "true",
        "access_token": token,
    })
    if "id" not in r:
        raise RuntimeError(f"la API no devolvió id para {url_video}: {r}")
    return r["id"]


def consultar(ruta, parametros):
    url = f"{API_HOST}/{API_VERSION}/{ruta}?" + urllib.parse.urlencode(parametros)
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=TIEMPO_ESPERA) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode(errors="replace")
        raise RuntimeError(f"error {e.code} al consultar el estado: {cuerpo[:300]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"sin conexion al consultar el estado: {e.reason}")


def esperar_a_que_este_listo(token, contenedor_id, etiqueta):
    """Igual que en publicar.py: sin esta espera, media_publish falla con
    «Media ID is not available» porque el vídeo aún se está procesando.
    """
    esperado = 0
    while True:
        r = consultar(contenedor_id, {"fields": "status_code", "access_token": token})
        estado = r.get("status_code", "DESCONOCIDO")
        if estado == "FINISHED":
            log(f"  {etiqueta}: listo tras {esperado}s")
            return
        if estado in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"{etiqueta}: Instagram devolvio estado {estado}")
        if esperado >= MAX_ESPERA_CONTENEDOR:
            raise RuntimeError(
                f"{etiqueta}: sigue en {estado} tras {esperado}s. No publico.")
        log(f"  {etiqueta}: {estado}, espero {ESPERA_CONTENEDOR}s")
        time.sleep(ESPERA_CONTENEDOR)
        esperado += ESPERA_CONTENEDOR


def publicar(token, user_id, creation_id):
    r = peticion("POST", f"{user_id}/media_publish", {
        "creation_id": creation_id,
        "access_token": token,
    })
    if "id" not in r:
        raise RuntimeError(f"la publicación no devolvió id: {r}")
    return r["id"]


def main():
    modo_prueba = "--prueba" in sys.argv
    de_verdad = os.environ.get("PUBLICAR_REELS_DE_VERDAD") == "1" and not modo_prueba

    hoy = os.environ.get("FECHA_FORZAR", "").strip() or datetime.date.today().isoformat()
    log(f"Fecha: {hoy} · modo: {'PUBLICAR' if de_verdad else 'REVISIÓN (no publica)'}")

    calendario = cargar_json(CALENDARIO, None)
    if calendario is None:
        error_y_salir("no encuentro calendario-reels.json")

    pieza = calendario.get(hoy)
    if not pieza:
        log("Hoy no toca reel. Nada que hacer.")
        return

    registro = cargar_json(REGISTRO, {})
    if hoy in registro:
        log(f"Hoy ya se publicó (id {registro[hoy].get('id')}). No repito.")
        return

    if not pieza.get("video"):
        error_y_salir("la pieza de hoy no tiene vídeo")
    if not pieza.get("pie", "").strip():
        error_y_salir("la pieza de hoy no tiene pie de publicación")
    MARCADORES = ("ACCIÓN DE CONVERSIÓN", "variante A o B", "[PENDIENTE", "[AQUÍ VA")
    encontrados = [m for m in MARCADORES if m in pieza["pie"]]
    if encontrados:
        error_y_salir("el pie tiene texto sin terminar y no se publica: "
                      + ", ".join(f'«{m}»' for m in encontrados))

    base = os.environ.get("BASE_URL", "").rstrip("/")
    url_video = f"{base}/{pieza['video']}"

    log(f"Pieza de hoy: {pieza.get('id')} — {pieza.get('titulo')}")
    log(f"Vídeo: {url_video}")
    log(f"Pie ({len(pieza['pie'])} caracteres):")
    log("  " + pieza["pie"].replace("\n", "\n  "))

    if not de_verdad:
        log("Modo revisión: no se publica nada. "
            "Pon PUBLICAR_REELS_DE_VERDAD=1 cuando quieras quitar el freno.")
        return

    token = os.environ.get("IG_TOKEN")
    user_id = os.environ.get("IG_USER_ID")
    if not token or not user_id:
        error_y_salir("faltan IG_TOKEN o IG_USER_ID")
    if not base:
        error_y_salir("falta BASE_URL")

    try:
        log("Creando el contenedor del reel...")
        creation_id = crear_contenedor_reel(token, user_id, url_video, pieza["pie"])

        log("Esperando a que Instagram procese el vídeo (puede tardar varios minutos)...")
        esperar_a_que_este_listo(token, creation_id, "el reel")

        log("Publicando...")
        publicacion_id = publicar(token, user_id, creation_id)

    except RuntimeError as e:
        error_y_salir(f"no se ha publicado nada. {e}")

    registro[hoy] = {
        "id": publicacion_id,
        "reel_id": pieza.get("id"),
        "titulo": pieza.get("titulo"),
        "publicado": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    guardar_json(REGISTRO, registro)
    log(f"PUBLICADO. Id de la publicación: {publicacion_id}")


if __name__ == "__main__":
    main()
