# Respaldo del publicador de Instagram

**Qué es.** Un flujo de n8n que cada día a las 18:00 (Europe/Madrid) comprueba si la pieza
de hoy se ha publicado. Si el cron de GitHub no ha llegado, dispara `publicar.yml` por API,
espera seis minutos, **vuelve a mirar el registro** y avisa por correo con lo que de verdad
ha pasado. Si ya estaba publicada, o si hoy no hay pieza en el calendario, no hace nada y
termina en silencio.

No sustituye al cron de GitHub: lo respalda.

**Por qué existe.** GitHub documenta el evento `schedule` como esfuerzo razonable, no
garantizado: puede retrasarse en periodos de alta carga y, si la carga es suficiente,
algunos trabajos encolados se descartan. Observado aquí: el 10-sep-2026 la ejecución llegó
con 67 minutos de retraso; el día 11 hubo que recuperarlo a mano.

## Los nueve nodos

`Schedule 18:00` → `Leer registro` → `Leer calendario` → `Decidir si hay que rescatar`
→ `Disparar el workflow` → `Esperar 6 minutos` → `Releer registro` →
`Comprobar el resultado` → `Avisar por correo`.

La verificación posterior es lo que evita el peor fallo posible: que el respaldo dispare,
GitHub acepte con un 204 y el workflow termine sin publicar nada. Eso pasa, por ejemplo,
si la variable `PUBLICAR_DE_VERDAD` no vale exactamente `1`: `publicar.py` entra en modo
revisión, la ejecución sale en verde y el registro no se toca. Sin releer el registro, el
correo diría "rescatado" cuando en Instagram no hay nada.

Tres desenlaces posibles, y cada uno tiene su correo:

| Situación | Correo |
|---|---|
| 204 y el día aparece en el registro | `[Instagram] Rescatado el día …` |
| GitHub responde 401 / 403 / 404 | `FALLO` — token de n8n caducado o sin permiso de Actions |
| 204 pero el registro sigue vacío | `FALLO` — arrancó y no publicó; mirar Actions |

No hay correo de "todo bien". Si llega un correo es porque hubo que intervenir.

## Cómo se levanta

1. **Actualizar `publicar.yml` primero.** Ver `publicar-yml-propuesto.md` en esta misma
   carpeta: tres crons y, sobre todo, el bloque `concurrency`. Sin ese cerrojo, si el
   respaldo y un cron coinciden, ambos leen `registro.json` antes de que ninguno lo haya
   escrito y el carrusel sale dos veces. **No actives el flujo de n8n antes de eso.**
2. Importar el JSON en n8n: Workflows → Import from File.
3. **Token de GitHub.** Fine-grained PAT limitado a este repositorio:
   - `Actions`: Read and write (disparar el workflow)
   - `Contents`: Read-only (leer registro y calendario)

   En n8n, credencial **Header Auth**: nombre `Authorization`, valor `Bearer <token>`.
   Asignarla a los **cuatro** nodos HTTP. Anotar la fecha de caducidad: el día que expire,
   el respaldo avisa con un `FALLO` de 401, no se cae en silencio.
4. **Credencial de Gmail** en `Avisar por correo`. Permisos mínimos: solo envío.
5. Comprobar la dirección de destino.
6. En Settings del flujo: zona horaria `Europe/Madrid` y flujo de error asignado.
7. Ejecutar a mano una vez con `Execute Workflow`.

## Cómo se comprueba que funciona de verdad

Forzar el caso que debe rescatar: en un día con pieza programada, antes de que pase el
cron de GitHub, ejecutar el flujo a mano. Debe disparar, llegar el correo de rescate y
aparecer la publicación. Hacerlo una vez. Un respaldo que nunca se ha probado no es un
respaldo.

Las lecturas van por `api.github.com`, no por `raw.githubusercontent.com`: raw sirve desde
caché unos minutos y podría devolver un registro viejo, disparando un rescate innecesario.

## Limitaciones asumidas

- **Depende de que la máquina esté encendida a las 18:00.** Si el cron de GitHub falla y
  n8n está apagado, el día se pierde igual. Esto tapa el fallo de GitHub, no el de casa.
  La solución real es mover n8n a algo que esté siempre encendido; no antes de tener datos
  de cuántas veces entra el respaldo.
- **Un día sin pieza no genera aviso.** Es correcto, pero significa que el silencio no
  prueba que todo vaya bien. El calendario actual termina el 6 de octubre de 2026.
- **El respaldo dispara una vez al día.** Si el problema es de fondo (token de Meta
  caducado), reintentará cada día y avisará cada día. La alerta es la señal; el arreglo
  es manual.

## Dónde vive

- Flujo en ejecución: n8n dentro de Ubuntu (`~/mpia`).
- Fuente versionada: el JSON de esta carpeta. La interfaz de n8n no es la copia de
  seguridad; cada cambio se reexporta aquí.
