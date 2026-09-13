# Respaldo del publicador de Instagram

**Qué es.** Un flujo de n8n que cada día a las 18:00 (Europe/Madrid) comprueba si la pieza
de Instagram de hoy se ha publicado. Si el cron de GitHub no ha llegado, dispara el
workflow `publicar.yml` por API y avisa por correo. Si ya está publicada, o si hoy no hay
pieza en el calendario, no hace nada y termina en silencio.

No sustituye al cron de GitHub: lo respalda. La vía principal sigue siendo `schedule` en
este mismo repositorio.

**Por qué existe.** GitHub documenta el evento `schedule` como esfuerzo razonable, no
garantizado: puede retrasarse en periodos de alta carga y, si la carga es suficiente,
algunos trabajos encolados se descartan. Observado aquí: el 10-sep-2026 la ejecución llegó
con 67 minutos de retraso; el día 11 hubo que recuperarlo a mano.

## Cómo se levanta

1. Importar el JSON en n8n: Workflows → Import from File.
2. **Cerrojo en el repositorio, antes de activar nada.** En `.github/workflows/publicar.yml`,
   al mismo nivel que `on:` y `permissions:`:

   ```yaml
   concurrency:
     group: publicar-instagram
     cancel-in-progress: false
   ```

   Sin esto, si las dos vías coinciden, ambas leerían `registro.json` antes de que ninguna
   lo hubiera escrito y se publicaría dos veces. Con el cerrojo, la segunda espera, hace su
   propio `checkout`, ve el registro actualizado y se retira sola.

3. **Token de GitHub.** Fine-grained PAT limitado a este repositorio:
   - `Actions`: Read and write (disparar el workflow)
   - `Contents`: Read-only (leer registro y calendario)

   En n8n, credencial **Header Auth**: nombre `Authorization`, valor `Bearer <token>`.
   Asignarla a los tres nodos HTTP. Anotar la fecha de caducidad del token: el día que
   expire, el respaldo deja de funcionar sin avisar.

4. **Credencial de Gmail** en el nodo `Avisar por correo`. Permisos mínimos: solo envío.
5. Comprobar la dirección de destino del correo.
6. En Settings del flujo: zona horaria `Europe/Madrid` y flujo de error asignado.
7. Ejecutar a mano una vez con `Execute Workflow` para verificar que las dos lecturas
   devuelven JSON válido.

## Cómo se comprueba que funciona de verdad

La prueba honesta es forzar el caso que debe rescatar: en un día con pieza programada,
antes de que el cron de GitHub haya pasado, ejecutar el flujo a mano. Debe disparar,
llegar el correo y aparecer la publicación. Hacerlo una vez; si no, no se sabe si el
respaldo funciona hasta el día que hace falta.

Las lecturas van por `api.github.com`, no por `raw.githubusercontent.com`: raw sirve desde
caché unos minutos y podría devolver un registro viejo, disparando un rescate innecesario.

## Limitaciones asumidas

- **Depende de que la máquina esté encendida a las 18:00.** Si el cron de GitHub falla y
  n8n está apagado, el día se pierde igual. Esto tapa el fallo de GitHub, no el de casa.
  La solución real es mover n8n a algo que esté siempre encendido; no antes de tener datos
  de cuántas veces entra el respaldo.
- **Un fallo dentro del workflow de GitHub no se detecta.** El flujo solo mira si el día
  está en `registro.json`. Si la ejecución arranca y falla (token de Meta caducado, imagen
  que no carga), el respaldo dispararía otra ejecución que fallaría igual. El correo de
  rescate es la pista: si llega y en Instagram no hay nada, el problema es otro.
- **Si el calendario se agota**, no hay pieza y el flujo calla. Eso es correcto, pero
  significa que el silencio no prueba que todo vaya bien. El calendario actual termina el
  6 de octubre de 2026.

## Dónde vive

- Flujo en ejecución: n8n dentro de Ubuntu (`~/mpia`).
- Fuente versionada: el JSON de esta carpeta. La interfaz de n8n no es la copia de
  seguridad; cada cambio se reexporta aquí.
