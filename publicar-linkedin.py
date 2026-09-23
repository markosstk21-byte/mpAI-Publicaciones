#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Publicador de carruseles en LinkedIn para el perfil de Marco Pavón Cobo.

Mismo planteamiento que publicar.py: lee un calendario, mira qué toca hoy y lo
publica. Va aparte a propósito — si LinkedIn falla, Instagram no se entera.

Diferencia importante con Instagram: LinkedIn NO descarga la imagen de una URL.
Hay que registrar la subida, mandarle el binario y quedarse con el identificador
que devuelve. Por eso este publicador sí descarga los PNG de GitHub Pages.

Uso:
    python publicar-linkedin.py --prueba    # no publica: enseña qué haría
    python publicar-linkedin.py             # publica (si PUBLICAR_DE_VERDAD=1)

Variables de entorno:
    LI_TOKEN            token de acceso de LinkedIn
    LI_PERSON_URN       urn:li:person:XXXX  (lo da linkedin-autorizar.py)
    LI_TOKEN_EXPIRA     opcional, "AAAA-MM-DD" en que caduca el token
    BASE_URL            dirección pública donde viven los PNG (GitHub Pages)
    PUBLICAR_DE_VERDAD  "1" para publicar; cualquier otra cosa = modo revisión
    FECHA_FORZAR        opcional, "AAAA-MM-DD" para recuperar un día perdido

El token de LinkedIn dura 60 días y los tokens de refresco programáticos solo
están disponibles para socios aprobados, así que toca reautorizar a mano cada
dos meses. Por eso existe LI_TOKEN_EXPIRA y el aviso de más abajo.
"""

import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

# ── Configuración ───────────────────────────────────────────────────────────────
# Rutas de la API de miembro (las que cubre el permiso w_member_social).
API_REGISTRO = "https://api.linkedin.com/v2/assets?action=registerUpload"
API_PUBLICAR = "https://api.linkedin.com/v2/ugcPosts"

TIEMPO_ESPERA = 60          # segundos de timeout por petición
REINTENTOS = 3
ESPERA_BASE = 5             # se duplica en cada reintento
PAUSA_ENTRE_IMAGENES = 2
AVISO_CADUCIDAD_DIAS = 10   # a partir de aquí, avisa de que el token se acaba

RAIZ = os.path.dirname(os.path.abspath(__file__))
CALENDARIO = os.path.join(RAIZ, "calendario-linkedin.json")
REGISTRO = os.path.join(RAIZ, "registro-linkedin.json")

# Mismos marcadores que en publicar.py. Publicar un texto a medias en el muro
# es peor que no publicar: se detiene siempre, también en modo publicación.
MARCADORES = ("ACCIÓN DE CONVERSIÓN", "variante A o B", "[PENDIENTE", "[AQUÍ VA")


# ── Utilidades ──────────────────────────────────────────────────────────────────
def log(msg):
    ahora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ahora}] {msg}", flush=True)


def error_y_salir(msg, codigo=1):
    log(f"ERROR: {msg}")
    sys.exit(codigo)


def _abrir(req):
    """Ejecuta una petición con reintentos solo ante errores temporales.

    Un 4xx que no sea 429 es permanente: reintentarlo solo gasta cuota. LinkedIn
    limita a 150 peticiones por miembro y día, así que esto importa.
    """
    espera = ESPERA_BASE
    for intento in range(1, REINTENTOS + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIEMPO_ESPERA) as r:
                cuerpo = r.read()
                return r.status, dict(r.headers), cuerpo
        except urllib.error.HTTPError as e:
            cuerpo = e.read().decode(errors="replace")
            temporal = e.code == 429 or e.code >= 500
            log(f"  respuesta {e.code} (intento {intento}/{REINTENTOS}): {cuerpo[:300]}")
            if e.code == 401:
                raise RuntimeError(
                    "401: el token no vale. Lo más probable es que haya caducado "
                    "(duran 60 días). Vuelve a autorizar con linkedin-autorizar.py")
            if not temporal:
                raise RuntimeError(f"error permanente {e.code}: {cuerpo[:300]}")
            if intento == REINTENTOS:
                raise RuntimeError(f"agotados los reintentos: {cuerpo[:300]}")
        except urllib.error.URLError as e:
            log(f"  red no disponible (intento {intento}/{REINTENTOS}): {e.reason}")
            if intento == REINTENTOS:
                raise RuntimeError(f"sin conexión con LinkedIn: {e.reason}")
        time.sleep(espera)
        espera *= 2
    raise RuntimeError("estado imposible en _abrir()")


def peticion_json(url, token, cuerpo=None, metodo="POST"):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(url, data=datos, method=metodo)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("X-Restli-Protocol-Version", "2.0.0")
    req.add_header("Content-Type", "application/json")
    _, cabeceras, salida = _abrir(req)
    texto = salida.decode(errors="replace")
    return (json.loads(texto) if texto.strip() else {}), cabeceras


def descargar(url):
    req = urllib.request.Request(url, method="GET")
    _, _, datos = _abrir(req)
    return datos


def cargar_json(ruta, por_defecto):
    if not os.path.exists(ruta):
        return por_defecto
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def guardar_json(ruta, datos):
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)


# ── Subida de imágenes ──────────────────────────────────────────────────────────
def registrar_subida(token, persona_urn):
    """Pide a LinkedIn un sitio donde dejar la imagen. Devuelve (url, urn)."""
    cuerpo = {
        "registerUploadRequest": {
            "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
            "owner": persona_urn,
            "serviceRelationships": [{
                "relationshipType": "OWNER",
                "identifier": "urn:li:userGeneratedContent",
            }],
        }
    }
    r, _ = peticion_json(API_REGISTRO, token, cuerpo)
    try:
        valor = r["value"]
        destino = (valor["uploadMechanism"]
                   ["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]
                   ["uploadUrl"])
        return destino, valor["asset"]
    except KeyError:
        raise RuntimeError(f"respuesta inesperada al registrar la subida: {r}")


def subir_binario(token, destino, datos):
    req = urllib.request.Request(destino, data=datos, method="PUT")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/octet-stream")
    _abrir(req)


def subir_imagen(token, persona_urn, url_imagen):
    datos = descargar(url_imagen)
    destino, urn = registrar_subida(token, persona_urn)
    subir_binario(token, destino, datos)
    return urn


# ── Publicación ─────────────────────────────────────────────────────────────────
def crear_publicacion(token, persona_urn, texto, urns, titulos):
    medios = [{
        "status": "READY",
        "media": urn,
        "title": {"text": titulo},
    } for urn, titulo in zip(urns, titulos)]

    cuerpo = {
        "author": persona_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": texto},
                "shareMediaCategory": "IMAGE",
                "media": medios,
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    r, cabeceras = peticion_json(API_PUBLICAR, token, cuerpo)
    # LinkedIn devuelve el identificador en la cabecera, y a veces también en el cuerpo.
    return cabeceras.get("x-restli-id") or r.get("id") or "(sin id)"


# ── Aviso de caducidad del token ────────────────────────────────────────────────
def avisar_si_caduca():
    """Devuelve los días que quedan, o None si no se ha configurado la fecha."""
    fecha = os.environ.get("LI_TOKEN_EXPIRA", "").strip()
    if not fecha:
        log("AVISO: no has puesto LI_TOKEN_EXPIRA, así que no puedo avisarte "
            "cuando el token esté a punto de caducar.")
        return None
    try:
        caduca = datetime.date.fromisoformat(fecha)
    except ValueError:
        log(f"AVISO: LI_TOKEN_EXPIRA no es una fecha válida: {fecha}")
        return None
    quedan = (caduca - datetime.date.today()).days
    if quedan < 0:
        log(f"AVISO: el token caducó hace {-quedan} días. Esto va a fallar.")
    elif quedan <= AVISO_CADUCIDAD_DIAS:
        log(f"AVISO: al token le quedan {quedan} días. Reautoriza con "
            "linkedin-autorizar.py antes de que se acabe.")
    else:
        log(f"Token vigente: le quedan {quedan} días.")
    return quedan


# ── Programa principal ──────────────────────────────────────────────────────────
def main():
    # Modo aviso: no publica nada, solo falla si al token le queda poco. Falla a
    # propósito, porque un trabajo fallido es lo que hace que GitHub te mande un
    # correo. Es el único aviso que no depende de que te acuerdes de mirar.
    if "--comprobar-token" in sys.argv:
        quedan = avisar_si_caduca()
        if quedan is None:
            error_y_salir("no puedo comprobar la caducidad: falta LI_TOKEN_EXPIRA")
        if quedan < 7:
            error_y_salir(
                f"quedan {quedan} días de token. Ejecuta linkedin-autorizar.py en "
                "tu ordenador y actualiza los secretos LI_TOKEN y LI_TOKEN_EXPIRA.")
        log(f"Token con margen suficiente ({quedan} días).")
        return

    modo_prueba = "--prueba" in sys.argv
    de_verdad = os.environ.get("PUBLICAR_DE_VERDAD") == "1" and not modo_prueba

    hoy = os.environ.get("FECHA_FORZAR", "").strip() or datetime.date.today().isoformat()
    log(f"Fecha: {hoy} · modo: {'PUBLICAR' if de_verdad else 'REVISIÓN (no publica)'}")

    avisar_si_caduca()

    calendario = cargar_json(CALENDARIO, None)
    if calendario is None:
        error_y_salir("no encuentro calendario-linkedin.json")

    pieza = calendario.get(hoy)
    if not pieza:
        log("Hoy no toca publicación en LinkedIn. Nada que hacer.")
        return

    registro = cargar_json(REGISTRO, {})
    if hoy in registro:
        log(f"Hoy ya se publicó (id {registro[hoy].get('id')}). No repito.")
        return

    if not pieza.get("imagenes"):
        error_y_salir("la pieza de hoy no tiene imágenes")
    texto = pieza.get("texto", "")
    if not texto.strip():
        error_y_salir("la pieza de hoy no tiene texto")
    encontrados = [m for m in MARCADORES if m in texto]
    if encontrados:
        error_y_salir("el texto tiene partes sin terminar y no se publica: "
                      + ", ".join(f'«{m}»' for m in encontrados))

    base = os.environ.get("BASE_URL", "").rstrip("/")
    urls = [f"{base}/{img}" for img in pieza["imagenes"]]

    log(f"Pieza de hoy: día {pieza.get('dia')} — {pieza.get('tema')}")
    log(f"Imágenes: {len(urls)}")
    for u in urls:
        log(f"  · {u}")
    log(f"Texto ({len(texto)} caracteres):")
    log("  " + texto.replace("\n", "\n  "))

    if not de_verdad:
        log("Modo revisión: no se publica nada. "
            "Pon PUBLICAR_DE_VERDAD=1 cuando quieras quitar el freno.")
        return

    token = os.environ.get("LI_TOKEN")
    persona = os.environ.get("LI_PERSON_URN")
    if not token or not persona:
        error_y_salir("faltan LI_TOKEN o LI_PERSON_URN")
    if not base:
        error_y_salir("falta BASE_URL")
    if not persona.startswith("urn:li:person:"):
        error_y_salir(f"LI_PERSON_URN no tiene la forma esperada: {persona}")

    try:
        log("Subiendo imágenes a LinkedIn...")
        urns = []
        for i, u in enumerate(urls, 1):
            urns.append(subir_imagen(token, persona, u))
            log(f"  {i}/{len(urls)} subida")
            time.sleep(PAUSA_ENTRE_IMAGENES)

        titulos = [f"{pieza.get('tema', 'MPAI')} — {i}/{len(urls)}"
                   for i in range(1, len(urls) + 1)]

        log("Publicando...")
        publicacion_id = crear_publicacion(token, persona, texto, urns, titulos)

    except RuntimeError as e:
        error_y_salir(f"no se ha publicado nada. {e}")

    registro[hoy] = {
        "id": publicacion_id,
        "dia": pieza.get("dia"),
        "tema": pieza.get("tema"),
        "publicado": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    guardar_json(REGISTRO, registro)
    log(f"PUBLICADO en LinkedIn. Id: {publicacion_id}")


if __name__ == "__main__":
    main()
