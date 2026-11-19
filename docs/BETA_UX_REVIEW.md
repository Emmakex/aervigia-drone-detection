# AERVIGIA — revisión visual de la beta local

**Fecha:** 19 de noviembre de 2026  
**Versión revisada:** v0.5.4 (solo simulación)  
**Fuente:** Capturas reales de Chromium, artefacto `aervigia-browser-qa` del workflow del [PR #12](https://github.com/Emmakex/aervigia-drone-detection/pull/12)

## Cobertura efectuada

Se inspeccionaron las capturas del panel en **1440 px** y **390 px**, además de las vistas de **incidentes revisados**, **histórico cerrado**, **escenario de entradas múltiples** y **acceso revocado**. El flujo automático también comprueba **320, 390, 768 y 1440 px** para detectar desbordamiento, objetivos táctiles inferiores a 44 px y contraste calculado de los botones de acción inferior a **4,5:1**. La navegación con teclado y el flujo completo de permisos están cubiertos por Chromium.

### Defectos corregidos

1. **Objetivos táctiles reducidos:** filtros y descargas de 38 px, y acciones de 40 px. Se normalizan a 44 px.
2. **Estado visual erróneo:** el punto de conexión seguía verde después de una revocación. Ahora utiliza verde para conexión válida, ámbar en espera y rojo ante errores.
3. **Tabla en móvil:** faltaba un indicio de que existían columnas a la derecha. Se muestra una instrucción de desplazamiento horizontal en anchuras pequeñas.
4. **Confirmación por teclado:** Escape cancela un reinicio de simulación pendiente y devuelve el foco al botón de inicio.
5. **Consistencia de idioma y sesión:** distintivo «SOLO SIMULACIÓN» y limpieza de confirmaciones antiguas al cambiar las credenciales.

### Resultado y límites

**Sin defectos visuales bloqueantes detectados para la beta local** en las capturas examinadas. El panel conserva las dimensiones adaptativas, la lectura de incidentes y un contraste adecuado en los controles comprobados.

Esto **no equivale** a validación con usuarios, pruebas en dispositivos físicos, auditoría WCAG completa ni autorización para desplegar en Internet. La aplicación continúa usando exclusivamente datos ficticios; cualquier despliegue público o conexión a sensores queda fuera de alcance.

**Criterio de cierre:** CI Python/JS/Docker y Chromium del PR en verde, e integración satisfactoria en `main`. La aceptación final del usuario sobre la estética sigue siendo independiente de estas verificaciones técnicas.

© 2026 Eduardo Yauri — todos los derechos reservados.
