# Publicador de LinkedIn

Publica en el perfil personal de Marco Pavón Cobo los mismos carruseles que van a
Instagram, con texto distinto. Va aparte de `publicar.py` a propósito: si LinkedIn
falla, Instagram no se entera.

---

## Lo que tienes que saber antes de empezar

**El token dura 60 días y hay que renovarlo a mano.** Los tokens de refresco
programáticos están reservados a socios aprobados de LinkedIn, así que esta parte no
se puede automatizar. No es un fallo del montaje: es cómo funciona la API.
Por eso el flujo incluye un aviso semanal que falla a propósito cuando quedan menos
de siete días, para que GitHub te mande un correo.

**Las publicaciones con varias imágenes hay que probarlas.** La documentación de
LinkedIn para publicar como miembro enseña el ejemplo con una sola imagen. El
publicador manda las nueve del carrusel, que es lo que queremos, pero eso hay que
verificarlo con una publicación real antes de fiarse. Si LinkedIn lo rechaza, el
apaño está abajo, en «Si algo falla».

---

## Puesta en marcha, una sola vez

### 1. Crear la aplicación

En el portal de desarrolladores de LinkedIn, crea una aplicación asociada a tu
perfil. En la pestaña de productos, solicita:

- **Share on LinkedIn** — es el que da el permiso `w_member_social`, el que
  permite publicar en tu propio perfil.
- **Sign In with LinkedIn using OpenID Connect** — solo se usa una vez, para
  averiguar tu identificador de persona.

Los dos son de acceso inmediato para el perfil propio. No hace falta página de
empresa ni programa de socios: eso es para publicar en nombre de una empresa, que no
es tu caso.

En la pestaña de autenticación, añade esta dirección de redirección, exactamente así:

```
http://localhost:8765/callback
```

Apunta el **Client ID** y el **Client Secret**.

### 2. Sacar el token

En tu ordenador, no en GitHub:

```
set LI_CLIENT_ID=lo-que-te-dio-linkedin
set LI_CLIENT_SECRET=lo-que-te-dio-linkedin
python linkedin-autorizar.py
```

Se abre el navegador, autorizas, y la consola te imprime los tres valores que
necesitas. El identificador de persona no cambia nunca; el token, cada 60 días.

### 3. Guardar los valores en el repositorio

En *Settings → Secrets and variables → Actions*:

**Secretos** (Secrets)

| Nombre | Qué es |
|---|---|
| `LI_TOKEN` | el token de acceso |
| `LI_PERSON_URN` | `urn:li:person:XXXXX` |

**Variables** (Variables)

| Nombre | Qué es |
|---|---|
| `LI_TOKEN_EXPIRA` | fecha de caducidad, `AAAA-MM-DD` |
| `PUBLICAR_LINKEDIN_DE_VERDAD` | `0` mientras pruebas, `1` para publicar |
| `BASE_URL` | ya existe, la comparte con Instagram |

El freno está separado del de Instagram a propósito: puedes tener Instagram
publicando y LinkedIn en revisión, o al revés.

### 4. Probar antes de soltarlo

Con `PUBLICAR_LINKEDIN_DE_VERDAD` en `0`, lanza el flujo a mano desde la pestaña
Actions con una fecha forzada, por ejemplo `2026-10-11`. En el registro verás las
URL de las imágenes y el texto entero, sin publicar nada.

Cuando eso se vea bien, pon la variable a `1` y vuelve a lanzarlo con esa misma
fecha. Esa es tu primera publicación de verdad, y es cuando se comprueba de una vez
lo de las varias imágenes.

---

## Cómo funciona por dentro

`calendario-linkedin.json` está indexado por fecha, igual que `calendario.json`:

```json
"2026-10-11": {
  "dia": 35,
  "tema": "Cinco señales de automatización",
  "imagenes": ["carrusel-dia-35/slide-01.png", "..."],
  "texto": "..."
}
```

El publicador, cada día:

1. Mira si hoy hay pieza. Si no, no hace nada.
2. Mira `registro-linkedin.json`. Si hoy ya se publicó, no repite.
3. Comprueba que hay imágenes, que hay texto, y que el texto no tiene marcadores
   sin terminar. Un texto a medias en el muro es peor que no publicar.
4. Descarga cada PNG de GitHub Pages. **LinkedIn no descarga imágenes de una URL
   como hace Instagram**: hay que registrar la subida, mandarle el binario y
   quedarse con el identificador que devuelve.
5. Crea la publicación con el texto y las imágenes.
6. Apunta el identificador en `registro-linkedin.json` y lo sube al repositorio.

Reintentos solo ante 429 y 5xx, igual que en Instagram. Un 401 se trata aparte y con
mensaje propio, porque casi siempre significa una sola cosa: el token ha caducado.

El cron son tres intentos por la mañana en vez de uno, por el mismo motivo que en
Instagram: el disparador de GitHub es esfuerzo razonable y no garantía, y el
publicador es idempotente, así que intentarlo tres veces no duplica nada.

---

## Cada 60 días

1. Ejecuta `linkedin-autorizar.py` en tu ordenador.
2. Actualiza `LI_TOKEN` y `LI_TOKEN_EXPIRA`.

Eso es todo. `LI_PERSON_URN` no cambia.

---

## Si algo falla

| Qué ves | Qué pasa |
|---|---|
| `401: el token no vale` | Ha caducado. Renuévalo con `linkedin-autorizar.py`. |
| El flujo del lunes falla | Es el aviso, funcionando. Quedan menos de 7 días de token. |
| Rechaza la publicación con varias imágenes | Deja solo la portada: en `calendario-linkedin.json`, recorta `imagenes` a la primera. Se pierde el carrusel pero la publicación sale. |
| `403` al subir la imagen | Falta el permiso `w_member_social`: revisa que el producto *Share on LinkedIn* esté concedido y vuelve a autorizar. |
| `no encuentro calendario-linkedin.json` | Se publicó el código sin el calendario. |
| Imagen que no se descarga | GitHub Pages no está sirviendo esa carpeta todavía. Abre la URL del registro en el navegador. |

LinkedIn limita a 150 peticiones por miembro y día. Un carrusel de nueve imágenes
gasta unas diecinueve, así que no es un problema salvo que se entre en un bucle de
reintentos: por eso los reintentos están limitados a tres y solo para errores
temporales.

---

## Lo que NO hace este flujo

- No publica en una página de empresa. No la tienes, y eso necesita otro permiso
  distinto y aprobación de LinkedIn.
- No publica los reels. Se puede añadir después, con el mismo esquema.
- No publica el carrusel como documento PDF nativo, que en LinkedIn suele rendir
  mejor que varias imágenes sueltas. Es la primera mejora que yo haría una vez esto
  lleve un par de semanas funcionando.
- No envía invitaciones ni mensajes. Solo publica.
