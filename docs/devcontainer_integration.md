# Intégration MemPalace dans un devcontainer

Ce guide explique comment rendre MemPalace disponible à l'intérieur d'un devcontainer VS Code via le montage du repo `mempalace-mcp-bridge`.

---

## Prérequis (hôte)

- Le repo `mempalace-mcp-bridge` est cloné sur la machine hôte :
  ```
  ~/git/mempalace-mcp-bridge
  ```
- `uv` est disponible dans l'image Docker du devcontainer.

---

## Étape 1 — Monter le repo dans le conteneur

Dans `docker-compose.yml` (ou directement dans `devcontainer.json` si tu n'utilises pas Compose), ajoute un volume **lecture seule** :

```yaml
# docker-compose.yml
services:
  dev:
    volumes:
      - ~/git/mempalace-mcp-bridge:/opt/mempalace-mcp-bridge:ro
```

> Le chemin cible `/opt/mempalace-mcp-bridge` est une convention ; tu peux en choisir un autre, mais il doit être cohérent avec les étapes suivantes.

---

## Étape 2 — Créer le répertoire hôte si absent (initializeCommand)

Pour éviter que Docker crée le répertoire source en tant que `root` si le clone n'existe pas encore, ajoute dans `devcontainer.json` :

```json
"initializeCommand": "mkdir -p ${localEnv:HOME}/git/mempalace-mcp-bridge"
```

Cette commande s'exécute **sur l'hôte**, avant la création du conteneur.

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
    echo 'MemPalace: non disponible, skip (montez ~/git/mempalace-mcp-bridge pour l'\''activer)'
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

VS Code Copilot démarrera automatiquement le serveur MCP au lancement du chat.

---

## Résumé des fichiers modifiés

| Fichier                          | Modification                                      |
|----------------------------------|---------------------------------------------------|
| `docker-compose.yml`             | Volume `~/git/mempalace-mcp-bridge:/opt/…:ro`    |
| `devcontainer.json`              | `initializeCommand` : `mkdir -p ~/git/mempalace-mcp-bridge` |
| `.devcontainer/post-create.sh`   | Bloc conditionnel `uv sync`                       |
| `.vscode/mcp.json`               | Config serveur MCP stdio                          |

---

## Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| `MemPalace: non disponible, skip` | `pyproject.toml` absent du repo hôte | Vérifier que le clone est complet et contient `pyproject.toml` |
| `MemPalace: non disponible, skip` | Volume non monté (Docker Desktop / WSL path) | Vérifier que le chemin hôte dans `docker-compose.yml` est correct |
| `uv: command not found` | `uv` absent de l'image | Ajouter `RUN pip install uv` ou l'installer dans le Dockerfile |
| Serveur MCP ne démarre pas | Chemin `--directory` incorrect dans `mcp.json` | S'assurer que `/opt/mempalace-mcp-bridge` correspond au mount cible |
