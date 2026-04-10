# Intégration MemPalace dans un devcontainer

Ce guide explique comment rendre MemPalace disponible à l'intérieur d'un devcontainer VS Code, avec le palace partagé entre l'hôte et le conteneur.

---

## Principe de conception

| Élément | Côté hôte | Côté conteneur |
|---|---|---|
| **Bridge MCP** (`mempalace-mcp-bridge`) | chemin libre — défini par `MEMPALACE_BRIDGE_HOST_DIR` | monté en lecture seule sur `/opt/mempalace-mcp-bridge` |
| **Palace** (`~/.mempalace`) | `~/.mempalace` | `~/.mempalace` du user conteneur |

Le **chemin hôte** est configurable : chaque développeur clone le repo où il veut.
Le **chemin conteneur** est fixe : `/opt/mempalace-mcp-bridge`. Les scripts, la config MCP et les hooks l'utilisent en dur — aucune hypothèse sur la machine hôte.

> Le bridge est monté **en lecture seule** depuis l'hôte vers `/opt/mempalace-mcp-bridge` à l'intérieur du conteneur. Le répertoire doit exister sur l'hôte — un mount vide ou absent casse l'intégration entière.

Le palace est partagé entre l'hôte et le conteneur : tout ce que l'agent mémorise dans le conteneur est directement visible sur l'hôte, et inversement.

---

## Prérequis (hôte)

> La seule exigence est que `MEMPALACE_BRIDGE_HOST_DIR` pointe vers un clone local valide de `mempalace-mcp-bridge` sur ta machine hôte.

1. Clone le repo `mempalace-mcp-bridge` à l'endroit de ton choix :

   ```bash
   git clone https://github.com/apajon/mempalace-mcp-bridge <chemin-de-ton-choix>
   # Exemple : /home/alice/src/mempalace-mcp-bridge, /opt/mempalace-mcp-bridge, etc.
   ```

2. Exporte la variable `MEMPALACE_BRIDGE_HOST_DIR` pointant vers ce clone, et rends-la permanente :

   ```bash
   # Utilise un chemin absolu (recommandé) :
   export MEMPALACE_BRIDGE_HOST_DIR=/absolute/path/to/mempalace-mcp-bridge

   # Ajoute cette ligne dans ~/.bashrc, ~/.zshrc ou équivalent pour la rendre permanente.
   ```

   > **Utilise toujours un chemin absolu.** Le tilde `~` peut ne pas être développé correctement selon l'environnement shell ou le contexte Docker, entraînant des erreurs silencieuses de mount.

   > **VS Code lancé depuis une interface graphique n'hérite pas des variables d'environnement du shell.** Si `MEMPALACE_BRIDGE_HOST_DIR` n'est pas visible depuis VS Code :
   > * soit définis la variable dans ton profil shell (`~/.bashrc`, `~/.zshrc`) et relance VS Code depuis un terminal (`code .`) ;
   > * soit lance toujours VS Code depuis un terminal où la variable est exportée.

3. Initialise le palace sur l'hôte si ce n'est pas encore fait :

   ```bash
   bash "$MEMPALACE_BRIDGE_HOST_DIR/setup.sh"
   ```

4. Vérifie que `uv` est disponible dans l'image Docker du devcontainer.

---

## Étape 1 — Valider la variable hôte (initializeCommand)

Dans `devcontainer.json`, ajoute un `initializeCommand` qui échoue tôt si la variable est absente ou pointe vers un répertoire inexistant. La commande s'exécute **sur l'hôte**, avant que Docker crée le conteneur :

```json
"initializeCommand": "test -n \"${MEMPALACE_BRIDGE_HOST_DIR}\" && test -d \"${MEMPALACE_BRIDGE_HOST_DIR}\" || (echo 'ERROR: MEMPALACE_BRIDGE_HOST_DIR is not set or does not exist. Export it to the path of your mempalace-mcp-bridge clone and rebuild.' && exit 1)"
```

Aucun répertoire n'est créé automatiquement. Si la variable est absente ou erronée, le build s'arrête avec un message explicite.

---

## Étape 2 — Monter le bridge et le palace

### Option A — docker-compose.yml

```yaml
services:
  dev:
    volumes:
      # Bridge MCP (lecture seule — le venv s'installe dans le conteneur)
      - ${MEMPALACE_BRIDGE_HOST_DIR}:/opt/mempalace-mcp-bridge:ro

      # Palace partagé avec l'hôte (lecture/écriture)
      - ~/.mempalace:/home/<container-user>/.mempalace
```

### Option B — devcontainer.json (sans Compose)

```json
"mounts": [
  "source=${localEnv:MEMPALACE_BRIDGE_HOST_DIR},target=/opt/mempalace-mcp-bridge,type=bind,consistency=cached,readonly",
  "source=${localEnv:HOME}/.mempalace,target=/home/<container-user>/.mempalace,type=bind"
]
```

> Remplace `<container-user>` par le nom d'utilisateur dans le conteneur (`dev`, `vscode`, `user`, etc.).
> Vérifie avec `whoami` dans un terminal du devcontainer.

---

## Étape 3 — Installer les dépendances et vérifier le palace (post-create)

Dans `post-create.sh`, ajoute le bloc suivant. Il installe les dépendances du bridge et exécute le health check pour détecter et corriger d'éventuelles incompatibilités ChromaDB :

```bash
MEMPALACE_DIR=/opt/mempalace-mcp-bridge

if [ -f "$MEMPALACE_DIR/pyproject.toml" ]; then
    echo 'MemPalace: installation des dépendances...'
    uv sync --directory "$MEMPALACE_DIR" --quiet
    echo 'MemPalace: vérification de la santé du palace...'
    bash "$MEMPALACE_DIR/scripts/check_palace_health.sh" || true
    echo 'MemPalace: prêt'
else
    echo 'MemPalace: non disponible, skip (définissez MEMPALACE_BRIDGE_HOST_DIR et reconstruisez le conteneur pour l'\''activer)'
fi
```

> `uv sync` installe `mempalace` dans le venv du bridge **dans le conteneur** — le mount `:ro` garantit qu'aucun fichier n'est écrit dans le repo hôte.
> `check_palace_health.sh` corrige silencieusement les incompatibilités ChromaDB
> (voir [troubleshooting.md#chromadb-version-incompatibility](troubleshooting.md#chromadb-version-incompatibility)).

---

## Étape 4 — Configurer le serveur MCP dans VS Code

Dans `.vscode/mcp.json` du workspace devcontainer :

```json
{
  "servers": {
    "mempalace": {
      "type": "stdio",
      "command": "/home/<container-user>/.local/bin/uv",
      "args": [
        "run",
        "--directory", "/opt/mempalace-mcp-bridge",
        "python", "-m", "mempalace.mcp_server"
      ],
      "env": {
        "MEMPALACE_PALACE_PATH": "/home/<container-user>/.mempalace/palace"
      }
    }
  }
}
```

**Pourquoi `MEMPALACE_PALACE_PATH` ?**
Sans cette variable, le serveur MCP cherche le palace dans le home du user courant du conteneur. La variable le rend explicite et prioritaire sur tout `config.json` hérité d'une autre machine.
Priorité de configuration : `MEMPALACE_PALACE_PATH` > `~/.mempalace/config.json` > défaut.

VS Code Copilot démarrera automatiquement le serveur MCP au lancement du chat.

---

## Résumé des fichiers à modifier

| Fichier | Modification |
|---|---|
| `devcontainer.json` | `initializeCommand` de validation + `mounts` avec `${localEnv:MEMPALACE_BRIDGE_HOST_DIR}` |
| `docker-compose.yml` | Volume bridge `${MEMPALACE_BRIDGE_HOST_DIR}:/opt/mempalace-mcp-bridge:ro` + palace bind mount |
| `post-create.sh` | Bloc conditionnel : `uv sync` + `check_palace_health.sh` |
| `.vscode/mcp.json` | Config serveur MCP avec `env.MEMPALACE_PALACE_PATH` |

---

## Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| `initializeCommand` échoue : `MEMPALACE_BRIDGE_HOST_DIR is not set` | Variable non exportée dans le shell qui lance VS Code | Ajouter `export MEMPALACE_BRIDGE_HOST_DIR=/absolute/path/to/mempalace-mcp-bridge` dans `~/.bashrc` ou `~/.zshrc`, puis lancer VS Code depuis un terminal (`code .`) et reconstruire |
| VS Code ne voit pas `MEMPALACE_BRIDGE_HOST_DIR` | VS Code lancé depuis l'interface graphique — il n'hérite pas des variables du shell | Définir la variable dans `~/.bashrc` ou `~/.zshrc`, puis lancer VS Code depuis un terminal (`code .`) |
| `initializeCommand` échoue : `does not exist` | Variable définie mais répertoire absent | Vérifier que `$MEMPALACE_BRIDGE_HOST_DIR` pointe vers la racine du clone et que celui-ci est bien présent |
| `MemPalace: non disponible, skip` | Mount vide — `pyproject.toml` absent | Vérifier que `MEMPALACE_BRIDGE_HOST_DIR` pointe vers la racine du repo (pas un sous-dossier) |
| Mount silencieusement vide (Docker Desktop / WSL) | Chemin Windows (`C:\...`) passé au lieu du chemin Linux | Utiliser le chemin Linux absolu (ex. `/home/user/src/mempalace-mcp-bridge`) dans `MEMPALACE_BRIDGE_HOST_DIR` |
| `"No palace found"` dans les outils MCP | Palace non monté ou `MEMPALACE_PALACE_PATH` absent/incorrect | Vérifier le bind mount `~/.mempalace` et la clé `env.MEMPALACE_PALACE_PATH` dans `mcp.json` |
| Palace présent sur l'hôte mais vide dans le conteneur | `<container-user>` incorrect dans le mount ou dans `MEMPALACE_PALACE_PATH` | Vérifier `whoami` dans le conteneur, corriger les deux occurrences de `<container-user>` |
| Serveur MCP ne démarre pas | Chemin `uv` incorrect dans `mcp.json` | Vérifier avec `which uv` dans un terminal du devcontainer et corriger la clé `command` |
| `uv: command not found` dans le conteneur | `uv` absent de l'image Docker | Ajouter `RUN pip install uv` dans le Dockerfile ou via un `onCreateCommand` |
