# Intégration MemPalace dans un devcontainer

Ce guide explique comment rendre MemPalace disponible à l'intérieur d'un devcontainer VS Code via le montage du repo `mempalace-mcp-bridge`.

**Principe de conception** : le clone du repo vit sur l'hôte à l'emplacement que tu choisis. Le devcontainer le monte en lecture seule à un chemin fixe (`/opt/mempalace-mcp-bridge`). Cela évite toute hypothèse machine-spécifique (ex. `~/git`) tout en gardant les scripts et la config MCP stables.

---

## Prérequis (hôte)

1. Clone le repo `mempalace-mcp-bridge` à l'endroit de ton choix sur la machine hôte :

   ```bash
   git clone https://github.com/apajon/mempalace-mcp-bridge ~/src/mempalace-mcp-bridge
   ```

   > `~/src` n'est qu'un exemple. Tu peux utiliser n'importe quel chemin.

2. Exporte la variable d'environnement `MEMPALACE_BRIDGE_HOST_DIR` pointant vers ce clone :

   ```bash
   export MEMPALACE_BRIDGE_HOST_DIR=~/src/mempalace-mcp-bridge
   ```

   Pour rendre ce réglage permanent, ajoute la ligne ci-dessus dans ton `~/.bashrc`, `~/.zshrc` ou équivalent.

3. `uv` est disponible dans l'image Docker du devcontainer.

---

## Étape 1 — Monter le repo dans le conteneur

Dans `docker-compose.yml` (ou directement dans `devcontainer.json` si tu n'utilises pas Compose), ajoute un volume **lecture seule** en utilisant `${localEnv:MEMPALACE_BRIDGE_HOST_DIR}` comme chemin source côté hôte :

```yaml
# docker-compose.yml
services:
  dev:
    volumes:
      - ${MEMPALACE_BRIDGE_HOST_DIR}:/opt/mempalace-mcp-bridge:ro
```

Ou dans `devcontainer.json` avec la syntaxe `localEnv` de VS Code :

```json
"mounts": [
  "source=${localEnv:MEMPALACE_BRIDGE_HOST_DIR},target=/opt/mempalace-mcp-bridge,type=bind,consistency=cached,readonly"
]
```

> Le chemin cible `/opt/mempalace-mcp-bridge` est **fixe** côté conteneur. Seul le chemin source (côté hôte) est configurable via `MEMPALACE_BRIDGE_HOST_DIR`.

---

## Étape 2 — Valider la variable hôte (initializeCommand)

Au lieu de créer un répertoire vide, utilise `initializeCommand` pour valider que `MEMPALACE_BRIDGE_HOST_DIR` est définie et pointe vers un répertoire existant. La commande s'exécute **sur l'hôte**, avant la création du conteneur :

```json
"initializeCommand": "test -n \"${MEMPALACE_BRIDGE_HOST_DIR}\" && test -d \"${MEMPALACE_BRIDGE_HOST_DIR}\" || (echo 'ERROR: MEMPALACE_BRIDGE_HOST_DIR is not set or does not exist. Export it to the path of your mempalace-mcp-bridge clone and rebuild.' && exit 1)"
```

Cette commande échoue tôt avec un message explicite si la variable est absente ou si le répertoire n'existe pas, avant même que Docker tente de monter le volume.

---

## Étape 3 — Installer les dépendances dans le post-create

Dans `post-create.sh`, ajoute le bloc conditionnel suivant. Il détecte si le mount est actif en vérifiant la présence du `pyproject.toml` :

```bash
# post-create.sh
MEMPALACE_DIR=/opt/mempalace-mcp-bridge

if [ -f "$MEMPALACE_DIR/pyproject.toml" ]; then
    echo 'MemPalace: installation des dépendances...'
    uv sync --directory "$MEMPALACE_DIR" --quiet
    echo 'MemPalace: prêt'
else
    echo 'MemPalace: non disponible, skip (définissez MEMPALACE_BRIDGE_HOST_DIR et reconstruisez le conteneur pour l'\''activer)'
fi
```

> `uv sync` lit le `pyproject.toml` du repo et installe `mempalace` dans le venv local du bridge. Le mount étant `:ro`, rien n'est écrit dans le repo hôte.

---

## Étape 4 — Configurer le serveur MCP dans VS Code

Dans le workspace devcontainer, crée ou complète `.vscode/mcp.json` :

```json
{
  "servers": {
    "mempalace": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "run",
        "--directory", "/opt/mempalace-mcp-bridge",
        "python", "-m", "mempalace.mcp_server"
      ]
    }
  }
}
```

Le chemin `/opt/mempalace-mcp-bridge` est toujours le même quel que soit l'endroit où tu as cloné le repo sur l'hôte.

VS Code Copilot démarrera automatiquement le serveur MCP au lancement du chat.

---

## Résumé des fichiers modifiés

| Fichier                          | Modification                                                                 |
|----------------------------------|------------------------------------------------------------------------------|
| `docker-compose.yml`             | Volume `${MEMPALACE_BRIDGE_HOST_DIR}:/opt/mempalace-mcp-bridge:ro`          |
| `devcontainer.json`              | `mounts` avec `${localEnv:MEMPALACE_BRIDGE_HOST_DIR}` ; `initializeCommand` de validation |
| `.devcontainer/post-create.sh`   | Bloc conditionnel `uv sync`                                                  |
| `.vscode/mcp.json`               | Config serveur MCP stdio                                                     |

---

## Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| `initializeCommand` échoue avec `MEMPALACE_BRIDGE_HOST_DIR is not set` | Variable non exportée sur l'hôte | Exécuter `export MEMPALACE_BRIDGE_HOST_DIR=<chemin>` dans le shell qui lance VS Code, puis reconstruire le devcontainer |
| `initializeCommand` échoue avec `does not exist` | `MEMPALACE_BRIDGE_HOST_DIR` pointe vers un répertoire inexistant | Vérifier que le chemin est correct et que le clone est présent |
| `MemPalace: non disponible, skip` | Le répertoire monté ne contient pas `pyproject.toml` | Vérifier que `MEMPALACE_BRIDGE_HOST_DIR` pointe vers la racine du repo `mempalace-mcp-bridge` et non vers un sous-répertoire |
| `MemPalace: non disponible, skip` | Volume non monté malgré la variable définie (Docker Desktop / WSL path) | Vérifier que le chemin hôte est accessible par Docker ; sur WSL, utiliser le chemin Linux (ex. `/home/user/...`) plutôt que `C:\...` |
| Serveur MCP ne démarre pas | Le mount a échoué silencieusement, `/opt/mempalace-mcp-bridge` est vide | Vérifier le mount avec `docker inspect <container>` ; reconstruire après avoir corrigé `MEMPALACE_BRIDGE_HOST_DIR` |
| Serveur MCP ne démarre pas | Chemin `--directory` incorrect dans `mcp.json` | S'assurer que `/opt/mempalace-mcp-bridge` correspond bien au chemin cible du mount |
| `uv: command not found` | `uv` absent de l'image | Ajouter `RUN pip install uv` ou l'installer dans le Dockerfile |
