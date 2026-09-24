"""Lightweight, modular UI translation (mirrors ``odoo_instance_manager``).

English is the source language: the string in the code is already English, so the
default UI needs no translation. When Spanish is selected, translation happens at
a few display/input chokepoints (see ``ui``/``prompts``) plus ``tf`` for
interpolated messages, so call sites barely change. Any string missing from the
catalog falls back to English, so partial translation degrades gracefully.

The catalog below is authored English→Spanish — the same direction it is read —
so an entry is looked up by exactly the literal that appears in the code.
"""

from __future__ import annotations

_LANG = "en"


def set_language(lang: str) -> None:
    global _LANG
    _LANG = "es" if str(lang).lower().startswith("es") else "en"


def current_language() -> str:
    return _LANG


def t(text: str) -> str:
    """Translate an English UI string to the current language (English → Spanish)."""
    return translate(text, _LANG)


def translate(text: str, lang: str) -> str:
    """Translate an English string to *lang*, whatever the session's language is.

    For the one kind of file rendered in a chosen language — a report written for
    a client — whose language is the report's, not the operator's."""
    if lang == "en":
        return text
    return _ES.get(text, text)


def tf(template: str, *args: object, **kwargs: object) -> str:
    """Translate a message template, then fill its ``{}``/``{name}`` placeholders.

    The English template is the catalog key, so interpolated messages translate
    too — e.g. ``tf("Already exists {}", path)`` looks up ``"Already exists {}"``.
    """
    return t(template).format(*args, **kwargs)


# The catalog: the English string in the code → its Spanish. English is the
# source language, so this is authored in the same direction it is looked up —
# an inverted catalog would silently merge two English strings whose Spanish
# happened to match.
_ES: dict[str, str] = {
    # startup / top-level menu
    "Idioma / Language": "Idioma / Language",
    "Odoo development & migration workspace generator":
        "Generador de workspaces de desarrollo y migración de Odoo",
    "- Generates and maintains per-client Odoo Community workspaces":
        "- Genera y mantiene workspaces de Odoo Community por cliente",
    "- Optional sections: system provisioning and migration (12→19)":
        "- Secciones opcionales: provisión del sistema y migración (12→19)",
    "- Shows the command plan before running anything":
        "- Muestra el plan de comandos antes de ejecutar nada",
    "\nWhat do you want to do?": "\n¿Qué quieres hacer?",
    "Workspaces (create / manage)": "Workspaces (crear / gestionar)",
    "System provisioning (optional)": "Provisión del sistema (opcional)",
    "Migration (OpenUpgrade 12→19)": "Migración (OpenUpgrade 12→19)",
    "Exit": "Salir",
    "\nExiting.": "\nSaliendo.",
    "\nOperation interrupted. Returning to the menu.":
        "\nOperación interrumpida. Volviendo al menú.",
    "\nInput closed. Exiting.": "\nEntrada cerrada. Saliendo.",
    "\n[ERROR] The operation did not complete: {}": "\n[ERROR] La operación no se completó: {}",
    # generic menu chrome
    "Back": "Volver",
    "Cancel": "Cancelar",
    "Select an option": "Selecciona una opción",
    "Enter the option number.": "Introduce el número de opción.",
    "Option out of range.": "Opción fuera de rango.",
    "No selection (0 to cancel).": "Sin selección (0 para cancelar).",
    "Execution plan": "Plan de ejecución",
    "Command finished with code {}.": "El comando terminó con código {}.",
    # prompt primitives
    "Value is required.": "Valor obligatorio.",
    "Answer 'yes'/'y' or 'no'/'n' (Enter = default).":
        "Responde 'sí'/'s' o 'no'/'n' (Enter = opción por defecto).",
    "Type exactly": "Escribe exactamente",
    "to confirm": "para confirmar",
    # apply / safety
    "To apply system changes, run with privileges (sudo).":
        "Para aplicar cambios en el sistema, ejecútalo con privilegios (sudo).",
    # migration
    "Generate a migration environment": "Generar un entorno de migración",
    "Clean a migration environment": "Limpiar un entorno de migración",
    "Which environment": "¿Qué entorno?",
    "No migration environments found under {}.": "No hay entornos de migración en {}.",
    "Also remove the shared clones cache (.repos)? It serves every migration environment.":
        "¿Eliminar también la caché compartida de clones (.repos)? La usan todos los entornos de migración.",
    "This permanently deletes {}.": "Esto elimina permanentemente {}.",
    "This permanently deletes {}, including the staged modules: {}.":
        "Esto elimina permanentemente {}, incluidos los módulos preparados (staging): {}.",
    "Cancelled.": "Cancelado.",
    "Migration environment removed.": "Entorno de migración eliminado.",
    "The PostgreSQL migration database (if any) is untouched — drop it with "
        "`dropdb -h 127.0.0.1 -U odoo {}` when you want a fully clean run.":
        "La base de datos PostgreSQL de migración (si existe) no se toca — bórrala con "
    "`dropdb -h 127.0.0.1 -U odoo {}` cuando quieras una ejecución totalmente limpia.",
    "Development PostgreSQL role": "Rol PostgreSQL de desarrollo",
    "Every generated file is already up to date.": "Todos los ficheros generados ya están al día.",
    "Only files that change are written; each existing one is kept as <file>.bak-<date> first.":
        "Solo se escriben los ficheros que cambian; antes se guarda cada uno existente como <fichero>.bak-<fecha>.",
    "Odoo {} states no Python maximum and is not known to build on {}; Python {} is recommended.":
        "Odoo {} no declara un Python máximo y no se sabe que compile en {}; se recomienda Python {}.",
    "Invalid PostgreSQL role: {}": "Rol PostgreSQL no válido: {}",
    "Remove migration environment {}": "Eliminar el entorno de migración {}",
    "Remove shared migration clones {}": "Eliminar la caché compartida de clones de migración {}",
    # preflight
    "Preflight check": "Comprobación previa (preflight)",
    "Source dump file to verify (empty to skip)":
        "Fichero de dump origen a verificar (vacío para omitir)",
    "Existing database to verify (empty to skip)":
        "Base de datos existente a verificar (vacío para omitir)",
    "Some required checks are MISSING — continue anyway?":
        "Faltan comprobaciones requeridas (MISSING) — ¿continuar de todos modos?",
    "Resolve the MISSING checks before running the migration.":
        "Resuelve las comprobaciones MISSING antes de ejecutar la migración.",
    "Preflight passed.": "Preflight superado.",
    # staging
    "Stage custom modules": "Preparar módulos custom (staging)",
    "Promote reviewed modules": "Promover módulos revisados",
    "Report on the runs so far": "Informe de las ejecuciones hasta ahora",
    "Follow a running migration": "Seguir una migración en marcha",
    "Following the run. Ctrl-C stops watching; the driver keeps going.":
        "Siguiendo la ejecución. Ctrl-C deja de mirar; el driver sigue.",
    "Nothing to follow yet: {} appears when the driver starts.":
        "Todavía no hay nada que seguir: {} aparece cuando arranca el driver.",
    "\nStopped watching. The driver is unaffected.":
        "\nDejamos de mirar. El driver no se ve afectado.",
    "Migration {} → {}": "Migración {} → {}",
    "Elapsed": "Tiempo",
    "{} — worth reading so far": "{} — lo que merece leerse hasta ahora",
    "  nothing above INFO yet": "  todavía nada por encima de INFO",
    "Reached outside its own machine": "Alcanzó fuera de su propia máquina",
    "The run finished: {}.": "La ejecución terminó: {}.",
    "Use \"Report on the runs so far\" for what each step logged and what is left open.":
        "Usa «Informe de las ejecuciones hasta ahora» para ver qué registró cada paso y qué queda abierto.",
    "Level": "Nivel",
    "Logger": "Logger",
    "Count": "Veces",
    "Message": "Mensaje",
    "pending": "pendiente",
    "ok": "ok",
    "fail": "falló",
    "skip": "omitido",
    "Create {}": "Crear {}",
    "Report written: {}": "Informe escrito: {}",
    "No run recorded yet in {} — the driver writes one line per event as it goes.":
        "Todavía no hay ninguna ejecución registrada en {} — el driver escribe una línea por evento según avanza.",
    "Step {} failed": "El paso {} falló",
    "exit {} — see {}": "salida {} — ver {}",
    "Step {} never finished": "El paso {} nunca terminó",
    "started {} and recorded no outcome": "empezó {} y no registró resultado",
    "Step {} passed with {} error line(s)": "El paso {} pasó con {} línea(s) de error",
    "first: {}": "la primera: {}",
    "{} step(s) never ran in this run": "{} paso(s) no se ejecutaron en esta pasada",
    "Decided ({})": "Decidido ({})",
    "OCA repositories this chain needs (comma-separated, optional)":
        "Repositorios de OCA que necesita esta cadena (separados por comas, opcional)",
    "Invalid OCA repository name(s): {}.": "Nombre(s) de repositorio OCA no válido(s): {}.",
    "OpenUpgrade now declares {} as its successor":
        "OpenUpgrade ahora declara {} como su sucesor",
    "{}: {}{}": "{}: {}{}",
    "Decision no longer holds ({})": "La decisión ya no se sostiene ({})",
    "{} was decided {} — {}": "{} se decidió como {} — {}",
    "File recording what you decided about modules with no successor (empty to skip)":
        "Fichero con lo que decidiste sobre módulos sin sucesor (vacío para omitir)",
    "the module now resolves in this step's sources":
        "el módulo ahora se resuelve en las fuentes de este paso",
    "A location for reviewed modules is required.":
        "Hace falta una ubicación para los módulos revisados.",
    "{} is inside the migration environments ({}), which cleaning deletes. "
    "Choose a location outside it.":
        "{} está dentro de los entornos de migración ({}), que la limpieza borra. Elige una ubicación fuera.",
    "Promote {} {} to {}": "Promover {} {} a {}",
    "Take {} stage {} from the promoted copy":
        "Tomar {} en el paso {} de la copia promovida",
    "Directory holding your reviewed modules, one subdirectory per version (empty = none)":
        "Directorio con tus módulos revisados, un subdirectorio por versión (vacío = ninguno)",
    "Which module": "¿Qué módulo?",
    "No staged modules in this environment.": "No hay módulos preparados en este entorno.",
    "Environment vs promoted": "Entorno vs promovido",
    "This replaces the promoted code of {} for: {}.":
        "Esto reemplaza el código promovido de {} para: {}.",
    "Promoted {} for: {}.": "Promovido {} para: {}.",
    "The promoted copy is yours: commit it on the branch for that version if you keep it in git. "
    "The throwaway repository inside each stage directory is not that history.":
        "La copia promovida es tuya: haz commit en la rama de esa versión si la llevas en git. El repositorio desechable que hay dentro de cada directorio de preparación no es ese histórico.",
    "same": "igual",
    "diverged": "divergen",
    "not promoted": "sin promover",
    "only promoted": "solo promovido",
    "The staging tool (odoo-module-migrator) is not installed. This plan installs it:":
        "La herramienta de staging (odoo-module-migrator) no está instalada. Este plan la instala:",
    "Directory containing your custom modules (at the source version)":
        "Directorio con tus módulos custom (en la versión origen)",
    "Modules to stage (comma-separated, empty = all)":
        "Módulos a preparar (separados por comas, vacío = todos)",
    "Not a directory: {}": "No es un directorio: {}",
    "Not found in the source directory: {}": "No están en el directorio origen: {}",
    "No modules to stage.": "No hay módulos que preparar.",
    "No OpenUpgrade clone for {} — candidate detection will be empty for those steps (generate the environment first).":
        "Sin clon de OpenUpgrade para {} — la detección de candidatos quedará vacía en esos pasos (genera antes el entorno).",
    "This replaces the already-staged code of: {}.": "Esto reemplaza el código ya preparado de: {}.",
    "Staging report: {}": "Informe de staging: {}",
    "Staging is a prepared starting point — your review completes the migration.":
        "El staging es un punto de partida preparado — tu revisión completa la migración.",
    # --- capability tables (provision check, migration preflight) ---
    'Host release': 'Versión del host',
    'Odoo build dependencies': 'Dependencias de compilación de Odoo',
    'PostgreSQL loopback auth': 'Autenticación loopback de PostgreSQL',
    'PostgreSQL version': 'Versión de PostgreSQL',
    'Development role ({})': 'Rol de desarrollo ({})',
    'Outbound firewall — OpenSnitch (optional)': 'Cortafuegos de salida — OpenSnitch (opcional)',
    'Mail capture — Mailpit (optional)': 'Captura de correo — Mailpit (opcional)',
    'Node.js (optional)': 'Node.js (opcional)',
    'rtlcss (optional)': 'rtlcss (opcional)',
    'uv (interpreters)': 'uv (intérpretes)',
    'Host python3': 'python3 del host',
    'all present': 'todas presentes',
    '{} missing': 'faltan {}',
    'not installed — PDF reports will fail': 'no instalado — los informes PDF fallarán',
    'installed and running': 'instalado y en ejecución',
    'installed but not running': 'instalado pero no está en ejecución',
    'present': 'presente',
    'not found': 'no encontrado',
    'could not be checked: PostgreSQL is not running':
        'no se pudo comprobar: PostgreSQL no está en ejecución',
    'could not be checked without sudo — run with sudo, or log in as the role once':
        'no se pudo comprobar sin sudo — ejecútalo con sudo, o entra una vez como el rol',
    'not installed (only for right-to-left languages)':
        'no instalado (solo para idiomas de derecha a izquierda)',
    'present — provides {}': 'presente — proporciona {}',
    'no interpreters listed': 'no lista intérpretes',
    'not installed (needed for migration steps and for any Odoo version the host python3 is out of range for — docs.astral.sh/uv)':
        'no instalado (necesario para los pasos de migración y para cualquier versión de Odoo fuera del rango del python3 del host — docs.astral.sh/uv)',
    '{} is not supported — supported: {}': '{} no está soportado — soportados: {}',
    '{} (un-patched — reports may be degraded)':
        '{} (sin parchear — los informes pueden degradarse)',
    '{} (no version declares a floor)': '{} (ninguna versión declara un mínimo)',
    '{} is below the {} Odoo {} requires': '{} es inferior al {} que requiere Odoo {}',
    '{} (Odoo {} requires {})': '{} (Odoo {} requiere {})',
    'trust for {} only': 'solo trust para {}',
    'PostgreSQL could not be asked for its rules — it may be stopped, the view needs sudo, or it reported a rule it could not parse; apply narrows the rules either way':
        'no se pudo preguntar a PostgreSQL por sus reglas — puede estar parado, la vista necesita sudo, o informó de una regla que no pudo interpretar; apply estrecha las reglas igualmente',
    'every role may connect over loopback without a password — apply narrows it to {}':
        'cualquier rol puede conectar por loopback sin contraseña — apply lo estrecha a {}',
    "{}'s loopback trust rule is missing or is never reached — apply adds one that is":
        'la regla de trust por loopback de {} falta o nunca se alcanza — apply añade una que sí',
    'config: unreadable': 'config: ilegible',
    'config: not valid JSON': 'config: no es JSON válido',
    '{} installed but not running': '{} instalado pero no está en ejecución',
    '{} running, not hardened: {}': '{} en ejecución, sin reforzar: {}',
    '{} running, hardened (default deny)': '{} en ejecución, reforzado (denegar por defecto)',
    '{} running — SMTP 127.0.0.1:1025, UI :8025':
        '{} en ejecución — SMTP 127.0.0.1:1025, interfaz :8025',
    'Addons layout': 'Layout de addons',
    'Source dump': 'Dump origen',
    'Database checks': 'Comprobaciones de base de datos',
    'Database version': 'Versión de la base de datos',
    'Installed modules': 'Módulos instalados',
    'Coverage ({})': 'Cobertura ({})',
    'Dropped by Odoo ({})': 'Eliminado por Odoo ({})',
    'Custom module {}': 'Módulo custom {}',
    'reachable': 'accesible',
    'not reachable': 'no accesible',
    'not installed (needed to build the native venvs)':
        'no instalado (necesario para construir los venvs nativos)',
    'not found (see provision)': 'no encontrado (ver provisión)',
    'could not check without sudo — run it with sudo, or connect as the role once':
        'no se pudo comprobar sin sudo — ejecútalo con sudo, o conéctate una vez como el rol',
    'skipped (no dump given)': 'omitido (no se indicó dump)',
    'skipped (no database named)': 'omitido (no se indicó base de datos)',
    'not readable: {}': 'no legible: {}',
    'pg_restore cannot list it — a custom-format dump (pg_dump -Fc) is required. {}':
        'pg_restore no puede listarlo — hace falta un dump en formato custom (pg_dump -Fc). {}',
    'addons/odoo<major>/{custom,oca} dirs absent — regenerate the environment':
        'faltan los directorios addons/odoo<major>/{custom,oca} — regenera el entorno',
    'cannot read ir_module_module (is it an Odoo database?)':
        'no se puede leer ir_module_module (¿es una base de datos de Odoo?)',
    'base {} matches source {}': 'base {} coincide con el origen {}',
    'base is {} but the environment was generated for source {}':
        'base es {} pero el entorno se generó para el origen {}',
    '{} installed': '{} instalados',
    "that step's sources are not on disk — generate the environment before reading coverage":
        'las fuentes de ese paso no están en disco — genera el entorno antes de leer la cobertura',
    "{} — place each module's {} branch in {}": '{} — coloca la rama {} de cada módulo en {}',
    '{} — not in {} and not renamed; OpenUpgrade removes them':
        '{} — no están en {} ni renombrados; OpenUpgrade los elimina',
    'needs per-version adapted code (and migrations/ scripts when data changes) — presence is not sufficient; see the staging workflow':
        'necesita código adaptado a cada versión (y scripts migrations/ cuando cambian datos) — estar presente no basta; ver el flujo de staging',
    # validation errors (models.py)
    'Invalid Odoo version: {!r} (supported: {}).':
        'Versión de Odoo no válida: {!r} (admitidas: {}).',
    'Invalid Python version: {!r} (expected e.g. 3.10).':
        'Versión de Python no válida: {!r} (se espera p. ej. 3.10).',
    'Invalid {}: {!r} (a whole number from 1 to {}).':
        '{} no válido: {!r} (un número entero de 1 a {}).',
    'Invalid workspace name: start with a lowercase letter, only [a-z0-9_], max 32 chars.':
        'Nombre de workspace no válido: empieza por minúscula, solo [a-z0-9_], máximo 32 caracteres.',
    'Invalid db_host: {!r} (a host name or IP address).':
        'db_host no válido: {!r} (un nombre de host o una dirección IP).',
    'Invalid db_user: {!r} (a PostgreSQL role).': 'db_user no válido: {!r} (un rol de PostgreSQL).',
    'Invalid working_db: {!r}.': 'working_db no válido: {!r}.',
    'The source ({}) must be older than the target ({}).':
        'El origen ({}) debe ser anterior al destino ({}).',
    'A workspace profile must be a JSON object, not {}.':
        'Un perfil de workspace debe ser un objeto JSON, no {}.',
    '{} is not a step in this chain ({}).': '{} no es un paso de esta cadena ({}).',
    'workspace profile': 'perfil de workspace',
    # the CLI's own help, printed by argparse before any menu
    'Create / manage per-client workspaces.': 'Crear y gestionar workspaces por cliente.',
    'Prepare a Linux host (optional).': 'Preparar un host Linux (opcional).',
    'Run an OpenUpgrade migration (12→19).': 'Ejecutar una migración OpenUpgrade (12→19).',
    "Stream every line a plan's commands print (default: one line per step, plus warnings and the output of a step that fails). Also ODWG_VERBOSE=1.":
        'Muestra cada línea que imprimen los comandos del plan (por defecto: una línea por paso, más los avisos y la salida de un paso que falla). También con ODWG_VERBOSE=1.',
    '(no output)': '(sin salida)',
    '{} — outside the supported range': '{} — fuera del rango soportado',
    'At least one Odoo version is required.':
        'Hace falta al menos una versión de Odoo.',
    'oca_repos must be a list of OCA repository names.':
        'oca_repos debe ser una lista de nombres de repositorios OCA.',
    'Invalid OCA repository name: {!r}.':
        'Nombre de repositorio OCA no válido: {!r}.',
    'Invalid db_user: {!r} (a PostgreSQL role: lowercase letters, digits and underscores, max 63 chars).':
        'db_user no válido: {!r} (un rol de PostgreSQL: minúsculas, dígitos y guiones bajos, máximo 63 caracteres).',
    # --- complete UI coverage (checked by tests/test_i18n.py) ---
    "English": "English",
    "Español": "Español",
    "The selected path for {} does not match the expected extensions: {}":
        "La ruta seleccionada para {} no coincide con las extensiones esperadas: {}",
    "Use this file anyway?": "¿Usar este fichero de todos modos?",
    "Select required file": "Selecciona el fichero requerido",
    "(default)": "(por defecto)",
    "Current directory": "Directorio actual",
    "  0) Choose a manual path": "  0) Introducir una ruta manual",
    "  ..) Up one level": "  ..) Subir un nivel",
    "  q) Cancel": "  q) Cancelar",
    "Choose a number, ..,  q, or a manual path": "Elige un número, .., q o una ruta manual",
    "Full file path": "Ruta completa del fichero",
    "Invalid input.": "Entrada no válida.",
    "Odoo {} supports Python {} — this host runs {}.":
        "Odoo {} soporta Python {} — este host usa {}.",
    "an undetected version": "una versión no detectada",
    "uv cannot provide Python {} on this host — install uv (provision check reports it) to build with it.":
        "uv no puede proporcionar Python {} en este host — instala uv (provision check lo indica) para usarlo.",
    "Keep the host python3 ({})": "Mantener el python3 del host ({})",
    "Build with uv Python {} (recommended)": "Usar Python {} de uv (recomendado)",
    "Choose another Python version": "Elegir otra versión de Python",
    "Interpreter for Odoo {}": "Intérprete para Odoo {}",
    "Python version (e.g. 3.10)": "Versión de Python (p. ej. 3.10)",
    "Python {} is outside the supported range for Odoo {} (bound: {}).":
        "Python {} está fuera del rango soportado por Odoo {} (límite: {}).",
    "Use it anyway?": "¿Usarlo de todos modos?",
    "\nWorkspaces": "\nWorkspaces",
    "Create a workspace": "Crear un workspace",
    "Manage an existing workspace": "Gestionar un workspace existente",
    "New workspace": "Nuevo workspace",
    "New (quick)": "Nuevo (rápido)",
    "From a profile file": "Desde un fichero de perfil",
    "Workspace name": "Nombre del workspace",
    "Odoo versions (comma-separated)": "Versiones de Odoo (separadas por comas)",
    "OCA repositories (comma-separated, optional)":
        "Repositorios OCA (separados por comas, opcional)",
    "Nothing to do.": "Nada que hacer.",
    "Odoo {} venv will use Python {}.": "El venv de Odoo {} usará Python {}.",
    "Workspace {} already exists — use manage to modify it.":
        "El workspace {} ya existe — usa gestionar para modificarlo.",
    "Workspace {} created.": "Workspace {} creado.",
    "No workspace.json in {} — cannot manage it.":
        "No hay workspace.json en {} — no se puede gestionar.",
    "No workspaces found.": "No se encontraron workspaces.",
    "Existing workspaces": "Workspaces existentes",
    "Manage {}": "Gestionar {}",
    "Refresh generated files": "Actualizar los ficheros generados",
    "Regenerate a venv": "Regenerar un venv",
    "Refresh shared repos": "Actualizar los repos compartidos",
    "Add a version": "Añadir una versión",
    "Which version": "¿Qué versión?",
    "This removes and rebuilds .venv/odoo{}.": "Esto elimina y reconstruye .venv/odoo{}.",
    "No present clones to refresh.": "No hay clones presentes que actualizar.",
    "New Odoo version (e.g. 19.0)": "Nueva versión de Odoo (p. ej. 19.0)",
    "{} is already in the workspace.": "{} ya está en el workspace.",
    "\nSystem provisioning": "\nProvisión del sistema",
    "Check host readiness": "Comprobar si el host está listo",
    "Apply (install what's missing)": "Aplicar (instalar lo que falte)",
    "Capability": "Capacidad",
    "{} is not supported — supported hosts: {}.": "{} no está soportado — hosts soportados: {}.",
    "Install rtlcss (with Node.js)? Only needed if users work in a right-to-left language (Arabic, Hebrew, Persian…)":
        "¿Instalar rtlcss (con Node.js)? Solo hace falta si los usuarios trabajan en un idioma de derecha a izquierda (árabe, hebreo, persa…)",
    "Host already provisioned — nothing to do.": "El host ya está provisionado — nada que hacer.",
    "Provisioning applied.": "Provisión aplicada.",
    "\nMigration (OpenUpgrade 12→19)": "\nMigración (OpenUpgrade 12→19)",
    "Source Odoo version (e.g. 13.0)": "Versión de Odoo origen (p. ej. 13.0)",
    "Target Odoo version (e.g. 18.0)": "Versión de Odoo destino (p. ej. 18.0)",
    "pinned by you": "fijado por ti",
    "recommended": "recomendado",
    "{} — the venv on disk was built with {}": "{} — el venv en disco se construyó con {}",
    "Step": "Paso",
    "Interpreter": "Intérprete",
    "Source": "Origen",
    "Pin a step to a specific Python version?": "¿Fijar un paso a una versión concreta de Python?",
    "Which step": "¿Qué paso?",
    "Python for Odoo {}": "Python para Odoo {}",
    "Pin it anyway?": "¿Fijarlo de todos modos?",
    "Migration chain: {}": "Cadena de migración: {}",
    "Apply this plan now?": "¿Aplicar este plan ahora?",
    "Environment ready. Run: bash {}/run_migration.sh <source-dump>":
        "Entorno listo. Ejecuta: bash {}/run_migration.sh <dump-origen>",
    "Create migrations directory for {} ({})": "Crear el directorio migrations de {} ({})",
    "State": "Estado",
    "Check": "Comprobación",
    "Detail": "Detalle",
    "Write {} (mode {})": "Escribir {} (modo {})",
    "Set mode {} on {}": "Fijar permisos {} en {}",
    "Clone Odoo {} into the shared cache": "Clonar Odoo {} en la caché compartida",
    "Clone OCA {} ({}) into the shared cache": "Clonar OCA {} ({}) en la caché compartida",
    "Create workspace directories for {}": "Crear los directorios del workspace {}",
    "Link OCA {} for Odoo {}": "Enlazar OCA {} para Odoo {}",
    "Back up {} to {}": "Guardar copia de seguridad de {} en {}",
    "Create directory for {}": "Crear el directorio de {}",
    "Update apt package lists": "Actualizar las listas de paquetes apt",
    "Install Odoo build dependencies": "Instalar las dependencias de compilación de Odoo",
    "Install PostgreSQL": "Instalar PostgreSQL",
    "Enable and start PostgreSQL": "Habilitar e iniciar PostgreSQL",
    "Create development role {} (if missing)": "Crear el rol de desarrollo {} (si falta)",
    "Trust loopback connections of {} for local development (pg_hba)":
        "Confiar en las conexiones loopback de {} para desarrollo local (pg_hba)",
    "Reload PostgreSQL": "Recargar PostgreSQL",
    "Ensure curl is available": "Asegurar que curl está disponible",
    "Download patched wkhtmltopdf ({})": "Descargar wkhtmltopdf parcheado ({})",
    "Verify wkhtmltopdf SHA-256 (abort on mismatch)":
        "Verificar el SHA-256 de wkhtmltopdf (aborta si no coincide)",
    "Install verified wkhtmltopdf .deb": "Instalar el .deb verificado de wkhtmltopdf",
    "Check that the patched wkhtmltopdf is the one on PATH":
        "Comprobar que el wkhtmltopdf del PATH es el parcheado",
    "Remove downloaded wkhtmltopdf .deb": "Eliminar el .deb descargado de wkhtmltopdf",
    "Install Node.js and npm": "Instalar Node.js y npm",
    "Install rtlcss globally": "Instalar rtlcss globalmente",
    "Clone OpenUpgrade {}": "Clonar OpenUpgrade {}",
    "Clone {} {}": "Clonar {} {}",
    "Core of the steps from 14.0 (the client runs {})": "Núcleo de los pasos desde la 14.0 (el cliente usa {})",
    "Core of the steps from 14.0": "Núcleo de los pasos desde la 14.0",
    "the client's core": "el núcleo del cliente",
    "your choice": "elegido por ti",
    "no identified client core": "sin núcleo del cliente identificado",
    "The steps from 14.0 run on {} ({}).": "Los pasos desde la 14.0 usan {} ({}).",
    "Invalid chain core: {!r} (one of {}).": "Núcleo de la cadena no válido: {!r} (uno de {}).",
    "Create requirements directory": "Crear el directorio de requirements",
    "Create uv venv (Python {}) for Odoo {}": "Crear el venv uv (Python {}) para Odoo {}",
    "Install psycopg2-binary for Odoo {}": "Instalar psycopg2-binary para Odoo {}",
    "Mark Odoo {} venv as ready": "Marcar el venv de Odoo {} como listo",
    "Mark the venv {} ready": "Marcar el venv {} como listo",
    "Create migration directories": "Crear los directorios de migración",
    "Create the staging tool venv": "Crear el venv de la herramienta de staging",
    "Install odoo-module-migrator": "Instalar odoo-module-migrator",
    "Create staging directories for {}": "Crear los directorios de staging de {}",
    "Copy {} stage {} from the {} stage": "Copiar {} etapa {} desde la etapa {}",
    "Prepare the git worktree for {} stage {}": "Preparar el worktree git de {} etapa {}",
    "Migrate {} code {} -> {}": "Migrar el código de {} {} -> {}",
    "Refresh Odoo {}": "Actualizar Odoo {}",
    "Refresh OCA {} ({})": "Actualizar OCA {} ({})",
    "Remove existing venv {}": "Eliminar el venv existente {}",
    "Create venv {} with uv (Python {})": "Crear el venv {} con uv (Python {})",
    "Create venv {}": "Crear el venv {}",
    "Upgrade pip/wheel/setuptools in {}": "Actualizar pip/wheel/setuptools en {}",
    "Install Odoo {} requirements": "Instalar los requisitos de Odoo {}",
    # --- the read-only surface ---
    'Source Odoo version (e.g. 12.0).': 'Versión de Odoo de origen (p. ej. 12.0).',
    'Target Odoo version (e.g. 19.0).': 'Versión de Odoo de destino (p. ej. 19.0).',
    'Print the cumulative run report. Writes nothing.':
        'Imprimir el informe acumulado de las ejecuciones. No escribe nada.',
    'Report what each tester probe found in a database. Reads only.':
        'Informar de lo que encontró cada sonda del tester en una base de datos. Solo lee.',
    'Database to read.': 'Base de datos a leer.',
    'Check the outbound firewall rules. Reads only.':
        'Comprobar las reglas del cortafuegos de salida. Solo lee.',
    "Compare the host's rules with the tool's own.":
        'Comparar las reglas del host con las propias de la herramienta.',
    "Check a database's outgoing mail. Reads only.":
        'Comprobar el correo saliente de una base de datos. Solo lee.',
    'Report whether mail can leave a database.':
        'Informar de si el correo puede salir de una base de datos.',
    'Cannot read {}.': 'No se puede leer {}.',
    'The {} rules are as the tool wrote them.':
        'Las reglas {} están como las escribió la herramienta.',
    '{} rule(s) to look at.': 'Hay {} regla(s) que mirar.',
    "Nothing was changed. Menu -> Provision -> Outbound firewall and mail capture rewrites the tool's own rules; your own are yours to judge.":
        'No se cambió nada. Menú -> Provision -> Cortafuegos de salida y captura de correo reescribe las reglas propias de la herramienta; las tuyas las juzgas tú.',
    "Menu -> Migration -> Capture a database's mail in Mailpit stops it.":
        'Menú -> Migración -> Capturar en Mailpit el correo de una base de datos lo detiene.',
    'No run recorded yet in {}.': 'Todavía no hay ninguna ejecución registrada en {}.',
    # --- the demo seed and module fates ---
    'Invalid module name: {}': 'Nombre de módulo no válido: {}',
    'Seed a demo source database': 'Sembrar una base de datos de origen con datos demo',
    'Module fates in this chain': 'Destino de los módulos en esta cadena',
    'Modules to ask about (comma-separated)':
        'Módulos por los que preguntar (separados por comas)',
    'Modules to install in the demo database (comma-separated, optional)':
        'Módulos a instalar en la base de datos demo (separados por comas, opcional)',
    'Modules found under the source version, with what this chain does to them:':
        'Módulos encontrados bajo la versión de origen, y lo que esta cadena hace con ellos:',
    'What the chain declares for the set you chose:':
        'Lo que la cadena declara para el conjunto que elegiste:',
    'carries on under its own name': 'sigue con su propio nombre',
    'absorbed into': 'absorbido por',
    'renamed to': 'renombrado a',
    'No apriori.py could be read for: {} — clone those steps before trusting this.':
        'No se pudo leer ningún apriori.py para: {} — clona esos pasos antes de fiarte de esto.',
    'No modules under {} — the seed will install core Odoo only.':
        'No hay módulos en {} — el seed instalará solo el core de Odoo.',
    'Now run {} — it builds the database and dumps it for the driver.':
        'Ahora ejecuta {} — construye la base de datos y hace el dump para el driver.',
    'Create the source add-ons directories for {}':
        'Crear los directorios de addons de origen para {}',
    # --- the rehearsal tester ---
    'Generate the migration tester': 'Generar el tester de migración',
    'Check the migration tester': 'Comprobar el tester de migración',
    'Create the tester tree for {}': 'Crear el árbol del tester para {}',
    'No analysis files read for {}.': 'No se leyó ningún fichero de análisis para {}.',
    'No OpenUpgrade analysis files were read: clone the environment first.':
        'No se leyó ningún fichero de análisis de OpenUpgrade: clona antes el entorno.',
    "{} probes, from this chain's own sources.":
        '{} sondas, sacadas de las fuentes de esta propia cadena.',
    'Classes this chain never exercises: {}':
        'Clases que esta cadena no ejercita nunca: {}',
    'Database to ask about the tester': 'Base de datos a la que preguntar por el tester',
    'The tester is not installed in {}.': 'El tester no está instalado en {}.',
    'The tester in {} declares no probe.': 'El tester de {} no declara ninguna sonda.',
    'Could not read the models of {}.': 'No se pudieron leer los modelos de {}.',
    '{} probe(s) need looking at in {}.': 'Hay {} sonda(s) que mirar en {}.',
    'Every probe behaved as its sources predicted in {}.':
        'Cada sonda se comportó en {} como predecían sus fuentes.',
    # --- egress control and mail capture ---
    "Capture a database's mail in Mailpit": 'Capturar en Mailpit el correo de una base de datos',
    "Restore a database's mail configuration":
        'Restaurar la configuración de correo de una base de datos',
    'Check whether a database can mail out':
        'Comprobar si una base de datos puede mandar correo fuera',
    'Create download directory {}': 'Crear el directorio de descarga {}',
    'Download {}': 'Descargar {}',
    'Verify {} SHA-512 (abort on mismatch)': 'Verificar el SHA-512 de {} (aborta si no coincide)',
    'Install OpenSnitch {} without starting it': 'Instalar OpenSnitch {} sin arrancarlo',
    'Remove downloaded packages': 'Eliminar los paquetes descargados',
    'Harden {}': 'Endurecer {}',
    "Replace the tool's own OpenSnitch rules ({}*)":
        'Sustituir las reglas propias de OpenSnitch ({}*)',
    'Enable and (re)start OpenSnitch': 'Habilitar y (re)iniciar OpenSnitch',
    'Download Mailpit {}': 'Descargar Mailpit {}',
    'Verify Mailpit SHA-256 (abort on mismatch)':
        'Verificar el SHA-256 de Mailpit (aborta si no coincide)',
    'Install Mailpit to {}': 'Instalar Mailpit en {}',
    'Remove downloaded files': 'Eliminar los ficheros descargados',
    'Enable and (re)start Mailpit': 'Habilitar y (re)iniciar Mailpit',
    'Capture the mail of database {} in Mailpit':
        'Capturar en Mailpit el correo de la base de datos {}',
    'Restore the mail configuration of database {}':
        'Restaurar la configuración de correo de la base de datos {}',
    'Install or update the outbound firewall (OpenSnitch)?':
        '¿Instalar o actualizar el cortafuegos de salida (OpenSnitch)?',
    'Install or update the local mail capture (Mailpit)?':
        '¿Instalar o actualizar la captura local de correo (Mailpit)?',
    'Check that {} connects over loopback': 'Comprobar que {} conecta por loopback',
    'Ask PostgreSQL to read back the rules for {}':
        'Preguntar a PostgreSQL por las reglas que tiene para {}',
    'OpenSnitch blocks every outbound connection without a rule, asking in its UI when it is open. Odoo may reach only localhost, plus DNS on port 53; the development tools keep their hosts. See docs/egress-control.md.':
        'OpenSnitch bloquea toda conexión saliente sin regla y pregunta en su interfaz cuando está abierta. Odoo solo puede llegar a localhost, más DNS en el puerto 53; las herramientas de desarrollo conservan sus destinos. Ver docs/egress-control.md.',
    'Database whose mail to capture': 'Base de datos cuyo correo capturar',
    'Database whose mail configuration to restore':
        'Base de datos cuya configuración de correo restaurar',
    'Database whose mail to check': 'Base de datos cuyo correo comprobar',
    'Invalid database name: {}': 'Nombre de base de datos no válido: {}',
    "The mail servers of {} will be deactivated and one pointing at Mailpit added. Nothing configured is overwritten: 'Restore the mail configuration' gives this database back exactly what it has now.":
        'Los servidores de correo de {} se desactivarán y se añadirá uno que apunta a Mailpit. No se sobrescribe nada de lo configurado: «Restaurar la configuración de correo» le devuelve a esta base de datos exactamente lo que tiene ahora.',
    '{} will mail out again through the servers it had before the capture. Do this when the database is going into production, not while it is still being rehearsed.':
        '{} volverá a mandar correo fuera por los servidores que tenía antes de la captura. Hazlo cuando la base de datos vaya a producción, no mientras se sigue ensayando.',
    'Could not read database {}.': 'No se pudo leer la base de datos {}.',
    'Could not read the mail configuration of {}.':
        'No se pudo leer la configuración de correo de {}.',
    'Mail can leave {}.': 'El correo puede salir de {}.',
    'Mail cannot leave {}.': 'El correo no puede salir de {}.',
    '{} has no active mail server: Odoo will use the smtp_server of its configuration file, whatever that points at.':
        '{} no tiene ningún servidor de correo activo: Odoo usará el smtp_server de su fichero de configuración, apunte a donde apunte.',
    'A capture is in effect: {} mail server(s) deactivated, not lost.':
        'Hay una captura en efecto: {} servidor(es) de correo desactivados, no perdidos.',
    ' — the capture': ' — la captura',
    '{} fetchmail server(s) are still fetching.':
        '{} servidor(es) fetchmail siguen recibiendo correo.',
    'Turn on {} (and at every start)': 'Encender {} (y en cada arranque)',
    'Turn off {} (and keep it off after a restart)':
        'Apagar {} (y mantenerlo apagado tras reiniciar)',
    "Remove the tool's own OpenSnitch rules ({}*)":
        'Eliminar las reglas propias de OpenSnitch ({}*)',
    'Purge OpenSnitch and the packages it pulled in':
        'Purgar OpenSnitch y los paquetes que arrastró',
    'Remove {}': 'Eliminar {}',
    'Remove the captured mail ({})': 'Eliminar el correo capturado ({})',
    'apt would remove {} package(s): {}': 'apt eliminaría {} paquete(s): {}',
    'Your own rules in {} are kept.': 'Tus propias reglas en {} se conservan.',
    'This removes the outbound firewall.': 'Esto elimina el cortafuegos de salida.',
    'This removes Mailpit and every message it captured.':
        'Esto elimina Mailpit y todos los mensajes que capturó.',
    'Done.': 'Hecho.',
    'not installed': 'no instalado',
    'on': 'encendido',
    'off': 'apagado',
    'running': 'en ejecución',
    'NOT running': 'NO está en ejecución',
    'A service is installed but not running. Check `systemctl status` for it: a unit that '
        'starts and then exits still leaves its install step reporting success.':
        'Hay un servicio instalado que no está en ejecución. Revisa `systemctl status`: una unidad que '
    'arranca y muere deja igualmente su paso de instalación informando de éxito.',
    'Component': 'Componente',
    'Version': 'Versión',
    'Neither is installed — use Apply to install them.':
        'No hay ninguno instalado — usa Aplicar para instalarlos.',
    '\nOutbound firewall and mail capture': '\nCortafuegos de salida y captura de correo',
    'Outbound firewall and mail capture (on/off, uninstall)':
        'Cortafuegos de salida y captura de correo (encender/apagar, desinstalar)',
    'Turn the outbound firewall off': 'Apagar el cortafuegos de salida',
    'Turn the outbound firewall on': 'Encender el cortafuegos de salida',
    'Uninstall the outbound firewall': 'Desinstalar el cortafuegos de salida',
    'Turn the mail capture off': 'Apagar la captura de correo',
    'Turn the mail capture on': 'Encender la captura de correo',
    'Uninstall the mail capture': 'Desinstalar la captura de correo',
    "Unload the kernel modules it used": "Retirar de memoria los módulos del kernel que usaba",
    'No verified patched wkhtmltopdf is pinned for {} — install it by hand (github.com/wkhtmltopdf/packaging) or PDF reports will be degraded.':
        'No hay ningún wkhtmltopdf parcheado y verificado fijado para {} — instálalo a mano (github.com/wkhtmltopdf/packaging) o los informes PDF saldrán degradados.',
    'Cannot read {}: {}': 'No se puede leer {}: {}',
    "Edit {} and run this again.": "Edita {} y vuelve a ejecutarlo.",
    "Make {} executable again": "Volver a hacer ejecutable {}",
    "These OCA repos are in the profile but not on disk: {}. The refreshed files name them "
    "in addons_path; run Refresh shared repos to clone and link them.":
        "Estos repos de OCA están en el perfil pero no en disco: {}. Los ficheros regenerados los "
        "nombran en addons_path; ejecuta «Refrescar repos compartidos» para clonarlos y enlazarlos.",
    "Adding {} moves the port of every later version: {}. Stop any instance you have "
    "running before applying, and use the new port afterwards.":
        "Añadir {} mueve el puerto de todas las versiones posteriores: {}. Para cualquier instancia "
        "que tengas en marcha antes de aplicar, y usa el puerto nuevo después.",
    "The venv for Odoo {} on disk was built with Python {}, outside the supported range "
    "({}). The refreshed files describe and rebuild it as it is.":
        "El venv de Odoo {} en disco se construyó con Python {}, fuera del rango soportado ({}). "
        "Los ficheros regenerados lo describen y lo reconstruyen tal cual.",
    'Cannot use the profile {}: {}': 'No se puede usar el perfil {}: {}',
    '{} names another workspace ({}).': '{} corresponde a otro workspace ({}).',
    "Not an Odoo module name: {}": "No es un nombre de módulo de Odoo: {}",
    "It also deletes the findings ledger and every client decision recorded in it — copy "
    "findings/ first if you need them.":
        "También borra el registro de hallazgos y todas las decisiones del cliente anotadas en "
        "él: copie findings/ antes si los necesita.",
    # --- taking in a client copy ---
    "Create database {}": "Crear la base de datos {}",
    "Restore {} into {} (errors kept in {})": "Restaurar {} en {} (errores guardados en {})",
    "Grant {} read access to {}, secrets excluded":
        "Dar a {} acceso de lectura a {}, sin los secretos",
    "Unpack {} into {}": "Desempaquetar {} en {}",
    "Make {} read-only": "Dejar {} en solo lectura",
    "Fetch the {} {} history (no file contents)":
        "Descargar la historia de {} {} (sin contenido de ficheros)",
    "Move the filestore into {}": "Mover el filestore a {}",
    "Copy {} to {}": "Copiar {} en {}",
    "Fetch {} {} at commit {}": "Descargar {} {} en el commit {}",
    "Create the read-only role {} (password to ~/.pgpass, never shown)":
        "Crear el rol de solo lectura {} (contraseña en ~/.pgpass, nunca se muestra)",
    "Refresh the {} {} history": "Actualizar la historia de {} {}",
    "Reference database (never modified)": "Base de referencia (nunca se modifica)",
    "Read-only role": "Rol de solo lectura",
    "Working copy database": "Base de datos de trabajo (copia)",
    "Client name (for the findings ledger)": "Nombre del cliente (para el registro de hallazgos)",
    "Flavour": "Variante",
    "Differing": "Distintos",
    "Patched": "Parcheados",
    "Client-only": "Solo del cliente",
    "Commit": "Commit",
    "{} will be created as a copy of {}. Neutralise it before starting Odoo on it.":
        "Se creará {} como copia de {}. Neutralízala antes de arrancar Odoo sobre ella.",
    "{} column(s) will be hidden from {}.": "Se ocultarán {} columna(s) a {}.",
    "{} core file(s) differ from official {} head; reading history…":
        "{} fichero(s) del core difieren del oficial {} actual; leyendo la historia…",
    "\nTake in a client copy ({} → {})": "\nRecibir una copia de cliente ({} → {})",
    "Intake recorded: {}": "Recepción anotada: {}",
    "No intake yet: restore the client's dump first.":
        "Todavía no hay recepción: restaura primero el dump del cliente.",
    "Client dump (pg_dump -Fc)": "Dump del cliente (pg_dump -Fc)",
    "Database {} exists (or cannot be checked); it is not replaced.":
        "La base de datos {} existe (o no se puede comprobar); no se sustituye.",
    "{} tables restored of {} in the dump: the reference may be incomplete.":
        "{} tablas restauradas de {} en el dump: la referencia puede estar incompleta.",
    "Client add-ons archive (.tar/.tar.gz)": "Archivo de addons del cliente (.tar/.tar.gz)",
    "Unpack the client's add-ons archive first.":
        "Desempaqueta primero el archivo de addons del cliente.",
    "Cannot read the configuration file.": "No se puede leer el fichero de configuración.",
    "Classify the client's add-ons archive first.":
        "Clasifica primero el archivo de addons del cliente.",
    "No core add-ons under {}.": "No hay addons del core en {}.",
    "Client filestore archive (.tar/.tar.gz)": "Archivo del filestore del cliente (.tar/.tar.gz)",
    "Identify the client's core first.": "Identifica primero el core del cliente.",
    "Finding {} is already in the ledger; left as it is.":
        "El hallazgo {} ya está en el registro; se deja como está.",
    "Client odoo.conf": "odoo.conf del cliente",
    "Take in a client copy": "Recibir una copia de cliente",
    "Restore the client's dump": "Restaurar el dump del cliente",
    "Create the read-only role": "Crear el rol de solo lectura",
    "Unpack the client's add-ons archive": "Desempaquetar el archivo de addons del cliente",
    "Classify the add-ons archive": "Clasificar el archivo de addons",
    "Identify the client's core": "Identificar el core del cliente",
    "Unpack the client's filestore": "Desempaquetar el filestore del cliente",
    "Build the client's source": "Montar el origen del cliente",
    "Copy the reference to a working database": "Copiar la referencia a una base de trabajo",
    "Show the intake": "Mostrar la recepción",
    "Fetch the OCA {} tree(s) for {}": "Descargar el árbol de OCA {} para {}",
    "Could not tell what the reference can act on; nothing recorded.":
        "No se pudo saber qué puede hacer la referencia hacia fuera; no se anota nada.",
    "No apriori.py read for: {}": "No se leyó ningún apriori.py para: {}",
    "The scanner fails its own control for: {}. No result is reported.":
        "El escáner falla su propio control en: {}. No se informa ningún resultado.",
    "Could not list OCA's repositories: gaps are provisional.":
        "No se pudieron listar los repositorios de la OCA: los huecos son provisionales.",
    "{} OCA tree(s) to fetch for the steps with gaps: {}":
        "{} árbol(es) de la OCA por descargar para los pasos con huecos: {}",
    "Survey what the copy can act on": "Sondear qué puede hacer la copia hacia fuera",
    "Check each installed module along the chain":
        "Comprobar cada módulo instalado a lo largo de la cadena",
    "Scan the client's own code for network calls":
        "Buscar llamadas de red en el código propio del cliente",
    "Install the client's modules' Python dependencies for {}":
        "Instalar las dependencias Python de los módulos del cliente para {}",
    "Comparing the client's core with {} sampled commits…":
        "Comparando el core del cliente con {} commits de muestra…",
    "No history to compare with.": "No hay historia con la que comparar.",
    # --- neutralising a copy of production ---
    "Check whether a database can act on the outside. Reads only.":
        "Comprueba si una base de datos puede actuar hacia fuera. Solo lee.",
    "Report crons, tax, payment and other integrations still able to act.":
        "Informa de los crons, integraciones fiscales, de pago y demás que aún pueden actuar.",
    "neutralise: the only action is 'check'": "neutralise: la única acción es 'check'",
    "Neutralise database {} (crons, tax and EDI, payments, IAP, links)":
        "Neutralizar la base de datos {} (crons, fiscal y EDI, pagos, IAP, enlaces)",
    "Give database {} its production settings back":
        "Devolver a la base de datos {} su configuración de producción",
    "Nothing was changed. Menu -> Migration (or a workspace) -> Neutralise a database turns "
    "it off.":
        "No se ha cambiado nada. Menú -> Migración (o un workspace) -> Neutralizar una base de "
        "datos lo desactiva.",
    "URL this copy is reached at (its links will point here)":
        "URL por la que se accede a esta copia (sus enlaces apuntarán aquí)",
    "Every cron of {} but housekeeping will be switched off, its mail captured, and its tax, "
    "EDI, payment, delivery, OAuth, calendar and IAP integrations taken out of production. "
    "Every value changed is recorded inside the database; only 'Give a neutralised database "
    "its production settings back' puts them back.":
        "Se desactivarán todos los crons de {} salvo los de limpieza, se capturará su correo y "
        "sus integraciones fiscales, EDI, de pago, transporte, OAuth, calendario e IAP saldrán "
        "de producción. Cada valor cambiado queda anotado dentro de la base de datos; solo "
        "'Devolver a una base neutralizada su configuración de producción' los restablece.",
    "{} will act on the outside again as production did: its crons run, its tax integration "
    "submits for real, its mail leaves through the client's servers. Do this on the day it "
    "goes into production, never on a copy being tested.":
        "{} volverá a actuar hacia fuera como producción: sus crons se ejecutan, su integración "
        "fiscal envía de verdad y su correo sale por los servidores del cliente. Hazlo el día "
        "que pase a producción, nunca en una copia en pruebas.",
    "{} row(s) did not exist in production and will stay neutralised:":
        "{} fila(s) no existían en producción y seguirán neutralizadas:",
    "No neutralisation is recorded in {}.": "No hay ninguna neutralización anotada en {}.",
    "Nothing in {} can act on the outside.": "Nada en {} puede actuar hacia fuera.",
    "{} can still act on the outside:": "{} todavía puede actuar hacia fuera:",
    "No active mail server: Odoo uses the configuration file's smtp_server. The tool's own "
    "configurations point it at the capture; one written elsewhere may not.":
        "No hay servidor de correo activo: Odoo usa el smtp_server del fichero de "
        "configuración. Las configuraciones de la herramienta lo apuntan a la captura; una "
        "escrita en otro sitio puede que no.",
    "Menu -> Neutralise a database turns it off.":
        "Menú -> Neutralizar una base de datos lo desactiva.",
    "mail: an active mail server points outside the capture":
        "correo: un servidor de correo activo apunta fuera de la captura",
    "Neutralise a database": "Neutralizar una base de datos",
    "Give a neutralised database its production settings back":
        "Devolver a una base neutralizada su configuración de producción",
    "Check whether a database can act on the outside":
        "Comprobar si una base de datos puede actuar hacia fuera",
    "Database to neutralise": "Base de datos a neutralizar",
    "Database to give its production settings back":
        "Base de datos a la que devolver su configuración de producción",
    "Database to check": "Base de datos a comprobar",
    "The role may not be allowed to read every column the check needs (a read-only role that "
    "hides secrets cannot answer it); run it as the database's owner.":
        "Puede que el rol no tenga permiso para leer todas las columnas que necesita la "
        "comprobación (un rol de solo lectura que oculta secretos no puede responderla); "
        "ejecútala como propietario de la base de datos.",
    # --- the findings ledger: commands and menu ---
    "Read the findings ledger and render its reports. Writes nothing.":
        "Lee el registro de hallazgos y genera sus informes. No escribe nada.",
    "List the findings; exits non-zero while a decision is pending.":
        "Lista los hallazgos; sale con código distinto de cero mientras quede una decisión "
        "pendiente.",
    "Print one finding in full.": "Muestra un hallazgo completo.",
    "The finding's id.": "El id del hallazgo.",
    "Check the ledger against its schema.": "Comprueba el registro contra su esquema.",
    "Print a report rendered from the ledger.": "Muestra un informe generado desde el registro.",
    "Which report (default: client).": "Qué informe (por defecto: client).",
    "The report's language, independent of --lang (default: en).":
        "El idioma del informe, independiente de --lang (por defecto: en).",
    "Request every URL in the ledger and name those that do not answer.":
        "Consulta cada URL del registro e indica las que no responden.",
    "No finding {} in the ledger.": "No hay ningún hallazgo {} en el registro.",
    "{} is valid.": "{} es válido.",
    "{} finding(s) await a decision. Menu -> Migration -> Findings -> Record a decision "
    "records one.":
        "{} hallazgo(s) pendientes de decisión. Menú -> Migración -> Hallazgos -> Anotar una "
        "decisión la registra.",
    "No findings ledger yet in {}.": "Todavía no hay registro de hallazgos en {}.",
    "{} link(s) answer.": "{} enlace(s) responden.",
    "No report was rendered:": "No se generó ningún informe:",
    "Client name": "Nombre del cliente",
    "Client database name": "Nombre de la base de datos del cliente",
    "Reference database (the restored copy never modified)":
        "Base de referencia (la copia restaurada que nunca se modifica)",
    "Which finding": "Qué hallazgo",
    "JSON file with the findings to add": "Fichero JSON con los hallazgos a añadir",
    "Who decided, and why": "Quién lo decidió y por qué",
    "Which phase": "Qué fase",
    "New state": "Nuevo estado",
    "Why it was wrong (kept in the corrections log)":
        "Por qué era incorrecto (queda en el registro de correcciones)",
    "Report language": "Idioma del informe",
    "\nFindings ({} → {})": "\nHallazgos ({} → {})",
    "No findings ledger yet in {}. Menu -> Migration -> Findings -> Start a findings ledger "
    "starts one.":
        "Todavía no hay registro de hallazgos en {}. Menú -> Migración -> Hallazgos -> Empezar "
        "un registro de hallazgos crea uno.",
    "Findings ledger written: {}": "Registro de hallazgos escrito: {}",
    "{} already exists; it is not replaced.": "{} ya existe; no se sustituye.",
    "The ledger holds no findings.": "El registro no contiene hallazgos.",
    "The findings ledger {} cannot be used:": "El registro de hallazgos {} no se puede usar:",
    "Nothing was changed:": "No se ha cambiado nada:",
    "No report was written:": "No se escribió ningún informe:",
    "Findings and client reports": "Hallazgos e informes para el cliente",
    "List the findings": "Listar los hallazgos",
    "Start a findings ledger": "Empezar un registro de hallazgos",
    "Add findings from a JSON file": "Añadir hallazgos desde un fichero JSON",
    "Record a decision": "Anotar una decisión",
    "Set a phase's state": "Cambiar el estado de una fase",
    "Withdraw a finding": "Retirar un hallazgo",
    "Write the reports": "Escribir los informes",
    # --- findings reports (rendered in the report's language, not the session's) ---
    "Generated from the findings ledger. Do not edit it: render it again.":
        "Generado desde el registro de hallazgos. No lo edite: vuelva a generarlo.",
    "Migration of Odoo {} to {}": "Migración de Odoo {} a {}",
    "Extended report — {} {} → {}": "Informe extendido — {} {} → {}",
    "Reference database (never modified): {}": "Base de referencia (nunca se modifica): {}",
    "report as of {}": "informe a fecha {}",
    "Where we are": "En qué punto estamos",
    "What we analysed": "Qué hemos analizado",
    "What was analysed": "Qué se ha analizado",
    "Versions": "Versiones",
    "Reference": "Referencia",
    "link": "enlace",
    "What we need you to confirm": "Lo que necesitamos que nos confirmen",
    "What we found": "Lo que hemos encontrado",
    "Important": "Importante",
    "Worth knowing": "A tener en cuenta",
    "For your information": "Para su información",
    "How we handle your data": "Cómo trabajamos con sus datos",
    "Reference links": "Enlaces de referencia",
    "What": "Qué",
    "Where": "Dónde",
    "Date": "Fecha",
    "Phase": "Fase",
    "Phases": "Fases",
    "Pending": "Pendiente",
    "In progress": "En curso",
    "Done": "Hecho",
    "Accepted": "Aceptado",
    "Act on it": "Actuar",
    "Declined": "Rechazado",
    "private repository": "repositorio privado",
    "Summary of findings": "Resumen de hallazgos",
    "Id": "Id",
    "Severity": "Gravedad",
    "Category": "Categoría",
    "Audience": "Público",
    "Found": "Detectado",
    "About": "Afecta a",
    "For the client": "Para el cliente",
    "Question": "Pregunta",
    "Evidence": "Evidencia",
    "How to check it again": "Cómo comprobarlo de nuevo",
    "Proposed action": "Acción propuesta",
    "Decision": "Decisión",
    "Earlier decisions": "Decisiones anteriores",
    "Corrections": "Correcciones",
    "Withdrawn": "Retirado",
    "Reason": "Motivo",
    'Rehearse uninstalling modules on a copy':
        'Ensayar la desinstalación de módulos en una copia',
    'Invalid module names: {}':
        'Nombres de módulo no válidos: {}',
    'No intake: {}':
        'No hay intake: {}',
    "Give {} a filestore of hard links to {}'s":
        'Dar a {} un filestore de hard links al de {}',
    'Uninstall {} on {} with Odoo {}':
        'Desinstalar {} en {} con Odoo {}',
    'Check that {} cannot act on the outside':
        'Comprobar que {} no puede actuar hacia fuera',
    'Neutralised working copy':
        'Copia de trabajo neutralizada',
    'Throwaway database':
        'Base de datos desechable',
    'Table':
        'Tabla',
    'Column':
        'Columna',
    'Kind':
        'Tipo',
    'Before':
        'Antes',
    'After':
        'Después',
    'Owned':
        'Propias',
    '{} will be created from {}, and {} uninstalled on it. {} itself is not modified.':
        'Se creará {} a partir de {} y se desinstalará {} en ella. {} no se modifica.',
    '{} is left in place for inspection; drop it when done.':
        '{} se deja para revisarla; bórrala cuando termines.',
    'Could not tell whether {} is neutralised.':
        'No se pudo saber si {} está neutralizada.',
    "{} can still act on the outside: run 'Neutralise a database' on it first.":
        "{} todavía puede actuar hacia fuera: ejecuta antes 'Neutralizar una base de datos' sobre ella.",
    'Not a working copy: {}':
        'No es una copia de trabajo: {}',
    'Not installed in {}: {}':
        'No instalados en {}: {}',
    'Could not compare the two databases; nothing recorded.':
        'No se pudieron comparar las dos bases de datos; no se registra nada.',
    'The uninstall took along: {}':
        'La desinstalación se llevó también: {}',
    'Modules to uninstall (comma-separated)':
        'Módulos a desinstalar (separados por comas)',
    'no client data lost':
        'no se pierden datos del cliente',
    'Uninstalling these also uninstalls: {}':
        'Desinstalar estos desinstala también: {}',
    "The client's modules declare Python libraries at these steps:":
        'Los módulos del cliente declaran librerías Python en estos pasos:',
    'Installed by the chain ({})':
        'Instalado por la cadena ({})',
    '{} — auto_install, and everything it needs is installed by then; checked from the next step on':
        '{} — auto_install, y todo lo que necesita está instalado para entonces; se comprueba desde el paso siguiente',
    '{} ({}): OCA has it in {} — add that repository when generating the environment':
        '{} ({}): la OCA lo tiene en {} — añade ese repositorio al generar el entorno',
    'Dependencies ({})':
        'Dependencias ({})',
    '{} — no source of this step has them':
        '{} — ninguna fuente de este paso las tiene',
    "Audit the client's own modules":
        'Auditar los módulos propios del cliente',
    'Find bank statement lines imported twice':
        'Buscar líneas de extracto bancario importadas dos veces',
    'From 14.0 every statement line already has its entry; this step is for a source up to 13.0, '
    'and the source is {}.':
        'Desde la 14.0 cada línea de extracto ya tiene su asiento; este paso es para un origen '
        'hasta la 13.0, y el origen es {}.',
    "Statements matching the bank's balances":
        'Extractos que cuadran con los saldos del banco',
    'Unreconciled lines':
        'Líneas sin conciliar',
    'Of them, certain duplicates':
        'De ellas, duplicados seguros',
    'Movements reconciled more than once':
        'Movimientos conciliados más de una vez',
    'Unreconciled lines after the lock date':
        'Líneas sin conciliar posteriores a la fecha de bloqueo',
    'Other modules to audit (comma-separated, optional)':
        'Otros módulos a auditar (separados por comas, opcional)',
    'Count use since (YYYY-MM-DD)':
        'Contar el uso desde (AAAA-MM-DD)',
    'Migrated database to check survival in (optional)':
        'Base de datos migrada donde comprobar que los datos siguen (opcional)',
    'Web access log to count prints from (optional)':
        'Log de accesos web para contar impresiones (opcional)',
    'Module':
        'Módulo',
    'Required by':
        'Lo necesitan',
    'Not a date, or not a database name.':
        'No es una fecha, o no es un nombre de base de datos.',
    'Could not read database {}; nothing recorded.':
        'No se pudo leer la base de datos {}; no se registra nada.',
    'Could not read {}; nothing recorded.':
        'No se pudo leer {}; no se registra nada.',
}

# Runtime lookup: English (the in-code source) → Spanish.
