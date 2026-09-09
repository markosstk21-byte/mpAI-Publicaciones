#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Publicador de carruseles en Instagram para @mpai.technologies.

Lee calendario.json, mira qué toca hoy y publica el carrusel del día usando la
API de Instagram (Instagram API with Instagram Login).

Uso:
    python publicar.py --prueba          # no publica: enseña qué haría
    python publicar.py                   # publica de verdad (si PUBLICAR_DE_VERDAD=1)

Variables de entorno necesarias:
    IG_TOKEN        token de acceso de larga duración de Meta
    IG_USER_ID      identificador de la cuenta de Instagram
    BASE_URL        dirección pública donde viven los PNG (GitHub Pages)
    PUBLICAR_DE_VERDAD   "1" para publicar; cualquier otra cosa = modo revisión

La API no acepta archivos: se le pasa la URL pública de cada imagen y ella la descarga.
"""

import json
import os
import sys
import time
import datetime
import urllib.request
import urllib.parse
import urllib.error

# ── Configuración ───────────────────────────────────────────────────────────────
# La versión de la API se fija aquí a propósito: no se usa "la última" para que una
# actualización de Meta no cambie el comportamiento sin avisar.
API_HOST = os.environ.get("IG_API_HOST", "https://graph.instagram.com")
API_VERSION = os.environ.get("IG_API_VERSION", "v23.0")

TIEMPO_ESPERA = 30          # segundos de timeout por petición
REINTENTOS = 3              # reintentos ante error temporal
ESPERA_BASE = 5             # segundos, se duplica en cada reintento
PAUSA_ENTRE_IMAGENES = 2    # segundos entre subidas de imagen
ESPERA_CONTENEDOR = 10      # segundos entre consultas del estado del contenedor
MAX_ESPERA_CONTENEDOR = 300 # 5 minutos: el limite que recomienda Meta

RAIZ = os.path.dirname(os.path.abspath(__file__))
CALENDARIO = os.path.join(RAIZ, "calendario.json")
REGISTRO = os.path.join(RAIZ, "registro.json")


# ── Utilidades ──────────────────────────────────────────────────────────────────
def log(msg):
    ahora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ahora}] {msg}", flush=True)


def error_y_salir(msg, codigo=1):
    log(f"ERROR: {msg}")
    sys.exit(codigo)


def peticion(metodo, ruta, parametros):
    """Llamada a la API con reintentos ante errores temporales.

    Un 4xx que no sea 429 es error permanente: reintentarlo solo gasta cuota.
    """
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


# ── Publicación ─────────────────────────────────────────────────────────────────
def crear_contenedor_imagen(token, user_id, url_imagen):
    r = peticion("POST", f"{user_id}/media", {
        "image_url": url_imagen,
        "is_carousel_item": "true",
        "access_token": token,
    })
    if "id" not in r:
        raise RuntimeError(f"la API no devolvió id para {url_imagen}: {r}")
    return r["id"]


def crear_carrusel(token, user_id, hijos, pie):
    r = peticion("POST", f"{user_id}/media", {
        "media_type": "CAROUSEL",
        "children": ",".join(hijos),
        "caption": pie,
        "access_token": token,
    })
    if "id" not in r:
        raise RuntimeError(f"la API no devolvió id del carrusel: {r}")
    return r["id"]


def consultar(ruta, parametros):
    """GET a la API. Se usa para preguntar por el estado de un contenedor."""
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
    """Espera a que Instagram termine de procesar un contenedor antes de publicarlo.

    Sin esta espera, media_publish falla con «Media ID is not available» (codigo 9007,
    subcodigo 2207027): el contenedor existe, pero todavia se esta procesando. Paso
    directamente vivido el 9-sep-2026 en la ejecucion #2.

    Meta recomienda consultar el estado como mucho durante cinco minutos.
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


# ── Programa principal ──────────────────────────────────────────────────────────
def main():
    modo_prueba = "--prueba" in sys.argv
    de_verdad = os.environ.get("PUBLICAR_DE_VERDAD") == "1" and not modo_prueba

    hoy = datetime.date.today().isoformat()
    log(f"Fecha: {hoy} · modo: {'PUBLICAR' if de_verdad else 'REVISIÓN (no publica)'}")

    calendario = cargar_json(CALENDARIO, None)
    if calendario is None:
        error_y_salir("no encuentro calendario.json")

    pieza = calendario.get(hoy)
    if not pieza:
        log("Hoy no toca carrusel. Nada que hacer.")
        return

    registro = cargar_json(REGISTRO, {})
    if hoy in registro:
        log(f"Hoy ya se publicó (id {registro[hoy].get('id')}). No repito.")
        return

    # Validación previa: mejor parar aquí que a medias
    if not pieza.get("imagenes"):
        error_y_salir("la pieza de hoy no tiene imágenes")
    if len(pieza["imagenes"]) > 10:
        error_y_salir("Instagram admite 10 imágenes como máximo por carrusel")
    if not pieza.get("pie", "").strip():
        error_y_salir("la pieza de hoy no tiene pie de publicación")
    # Marcadores de texto sin terminar. Publicar uno de estos en el muro sería peor
    # que no publicar nada: se detiene siempre, incluso en modo publicación.
    MARCADORES = ("ACCIÓN DE CONVERSIÓN", "variante A o B", "[PENDIENTE", "[AQUÍ VA")
    encontrados = [m for m in MARCADORES if m in pieza["pie"]]
    if encontrados:
        error_y_salir("el pie tiene texto sin terminar y no se publica: "
                      + ", ".join(f'«{m}»' for m in encontrados))

    base = os.environ.get("BASE_URL", "").rstrip("/")
    urls = [f"{base}/{img}" for img in pieza["imagenes"]]

    log(f"Pieza de hoy: día {pieza.get('dia')} — {pieza.get('tema')}")
    log(f"Imágenes: {len(urls)}")
    for u in urls:
        log(f"  · {u}")
    log(f"Pie ({len(pieza['pie'])} caracteres):")
    log("  " + pieza["pie"].replace("\n", "\n  "))

    if not de_verdad:
        log("Modo revisión: no se publica nada. "
            "Pon PUBLICAR_DE_VERDAD=1 cuando quieras quitar el freno.")
        return

    token = os.environ.get("IG_TOKEN")
    user_id = os.environ.get("IG_USER_ID")
    if not token or not user_id:
        error_y_salir("faltan IG_TOKEN o IG_USER_ID")
    if not base:
        error_y_salir("falta BASE_URL")

    try:
        log("Subiendo imágenes...")
        hijos = []
        for i, u in enumerate(urls, 1):
            hijos.append(crear_contenedor_imagen(token, user_id, u))
            log(f"  {i}/{len(urls)} lista")
            time.sleep(PAUSA_ENTRE_IMAGENES)

        log("Creando el carrusel...")
        creation_id = crear_carrusel(token, user_id, hijos, pieza["pie"])

        log("Esperando a que Instagram procese el carrusel...")
        esperar_a_que_este_listo(token, creation_id, "el carrusel")

        log("Publicando...")
        publicacion_id = publicar(token, user_id, creation_id)

    except RuntimeError as e:
        error_y_salir(f"no se ha publicado nada. {e}")

    registro[hoy] = {
        "id": publicacion_id,
        "dia": pieza.get("dia"),
        "tema": pieza.get("tema"),
        "publicado": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    guardar_json(REGISTRO, registro)
    log(f"PUBLICADO. Id de la publicación: {publicacion_id}")


if __name__ == "__main__":
    main()
