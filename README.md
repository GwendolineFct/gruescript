# Script ansible-migrator

## Caractéristiques

La fonction première de ce script est d'aider à migrer les playbooks ansible pour le passage à la version 2.12

En effet à partir de la 2.10, ansible impose le système des collections:

- dans les tasks il faut utiliser le Fully Qualified Collection Name (`FQCN`) d'un module
- les collections doivent être installées en amont en utilisant `ansile-galaxy`


```bash
$ ansible_migrator.py [-h] [-O] [-L LOG_PATH] [-l] [-N] [-H] [-v] [-q] [-s VERSION] [-t VERSION] [-c] [-C PATH] [-G COLLECTION] PATH
```

- `PATH`                Si `PATH` pointe sur un fichier, alors seul ce fichier sera migré.
                        Si `PATH` pointe sur un répertoire, alors ce répertoire et ses sous-répertoires seront scannée pour y trouver des fichiers à migrer. 
- `-h` ou `--help`      Affiche ceci
- `-O` ou `--overwrite-source` 
                        Effectue les modifications dans les fichiers sources
- `-L LOG_PATH` ou `--store-logs LOG_PATH`
                        Stocke les logs de migrations à l'emplacement spécifié. par défaut les logs ne sont pas conversées
- `-l` ou `--logs`      Affiche les logs de migrations dans la console à la fin de la migration
- `-N` ou `--no-logs-in-files`
                        Empêche l'insertions des log de migrations sous la commentaires dans les fichiers migrés
- `-H` ou `--hidden-files`    Autorise le traitement des fichiers/répertoires cachés (commençant avec un `.`)
- `-v` ou `--verbose`   Augmente la verbosité du script. Peut-être répété plusieurs fois pour augmenter d'autant plus la verbosité
- `-q` ou `--quiet`     Diminue la verbosité du script. Peut-être répété plusieurs fois pour augmenter d'autant plus la verbosité
-  `-c` ou `--cache-downloaded-modules`
                        Génère un fichier de cache (`downloaded-modules.cache.yml`) dans le répertoire courant pour les modules qui auront été téléchargés durant la migration
- `-C PATH` ou `--cache-path PATH`
                        Specifie ou chercher des fichiers de cache de définition des modules. Sert aussi à specifier ou stocker les fichiers de cache de collections (voir l'option `--generate-cache-for-collection`). Cette option ne change pas l'emplacement du fichier `downloaded-modules.cache.yml`. Il est possible de répéter cette options pour charger à partir de plusieurs emplacements. Par défaut cherche les fichiers cache dans le répertoire `./cache`.
- `-G COLLECTION`, `--generate-cache-for-collection COLLECTION`
                        Génère un fichier cache pour la collections spécifiée. Il est possible de spécifier plusieurs fois cette options pour cacher plusieurs collections. Si `--cache-path` contient plusieurs répertoire, seul le premier sera utilisé pour la sauvegarde du cache des collections


En mode migration d'un répertoire, le script cherche des fichiers qui matchent `*.y(a)ml` mais pas `*.migrated.y(a)ml` ni `*.cache.y(a)ml`. Le script effectue une analyse syntaxique pour dédicer ou non de migrer un fichier. Si celui-ci ressemble à un playbook ou à une liste de tâches, alors il sera migré, sinon il sera ignoré.

Par défaut le script crée une version "migrée" de chaque fichier qu'il migre. Pour ce faire il insère un `.migrated` dans le nom du fichier. Il est possible de modifier directement les fichiers sources avec l'option `--overwrite-source`. Il est conseillé de faire un backup ou d'utiliser `git` avant de lancer le script.

Le script insère des commentaires (sauf si l'option `no-logs-in-files`) dans les fichiers pour indiquer ce qui a été fait. Il insère également des warnings si il détecte des breaking changes

Liste non exhaustive des type de commentaires
- module supprimé dans la nouvelle version
- renomage d'un alias par le vrai nom du paramètre
- paramètre supprimé dans la nouvelle version
- paramètre non specifié désormais obligatoire
- paramètre non spécifié dont la valeur par défaut à changé
- valeur d'un paramètre (potentiellement) hors de la liste de choix possible
- type d'un paramètre plus restrictif (ie string -> number)
- breaking change dans les facts remontés
- breaking change dans les valeurs retournées dans le cas où un register est spécifié dans la tâche
- etc ...

Il est a noter que ce script n'est pas capable d'interpoler les expressions ansible du type "{{ foobar }}". Dans ce cas il indiquera des warnings si besoin. Il en va de même avec les modules dont les paramètres sont spécifié en `free-form`. De même le script ne suit pas les `includes_xxx` pour trouver quoi analyser. Il scanne tous les répertoires de manière récursive pour trouver ce qui doit être migré.

Le script est aussi capable de générer des fichiers de cache  pour des collections afin de rendre les migrations plus rapide. Attention ces fichiers cache sont prévu pour migrer de la version 2.9 à la version latest (2.12). Si la version source ou cible change il convient de supprimer ces fichiers et de les regénérer.

Il est aussi possible de spécifier un emplacement de fichiers cache au moyen de la variable d'environement `ANSIBLE_MIGRATOR_CACHE_PATH`. Si celle ci est présente elle sera ajoutée en début de liste. Il est possible de specifier plusieurs emplacement dans cette variable en séparant les valeurs avec des `:`.
```bash
export ANSIBLE_MIGRATOR_CACHE_PATH="/opt/ansible/ansible-migrator/cache:/etc/ansible-migrator/cache"
```
Dans le cas où un module serait défini dans plusieurs fichiers cache, les données seront mises à jour dans l'ordre de lecture des répertoires de cache.


### Récupération des informations des modules

Lorsque le script rencontre un module qu'il ne connait pas il va chercher:
- la doc du module en 2.9 à l'adresse `https://docs.ansible.com/ansible/29/modules/{module_name}_module.html`
- s'il ne le trouve pas:
  - suppose que le module est déjà désigné par son FQCN
  - essaye à l'adresse `https://docs.ansible.com/ansible/latest/collections/{module_fqcn}_module.html`
  - puis récupère la doc 2.9  à l'adresse `https://docs.ansible.com/ansible/29/collections/{module_fqcn}_module.html`
- sinon:
  - recupère la doc du module en latest à l'adresse `https://docs.ansible.com/ansible/latest/modules/latest_module.html`
- récupérer pour chaque version les paramètres, les retours ainsi que les éventuels facts

Dans le cas de la génération d'un fichier cache pour une collecion (option `--generate-cache-for-collection`) le script procède comme suit:
- récupération de la liste des modules de la collection à l'adresse `https://docs.ansible.com/ansible/latest/collections/{collection}/index.html`
- pour chaque module dans la liste récupère les informations du module comme précédemment

### Logs d'éxécution

les logs d'éxécution sont au format suivant:
`TEMPS NIVEAU : MESSAGE`
- `TEMPS`: temps en millisecondes depuis le démarrage du script
- `NIVEAU`: le niveau de sévérité du message (PRINT > FATAL > ERROR > WARN > INFO > DEBUG > TRACE)
- `MESSAGE`: le message de la trace

Par défaut les messages INFO et au delà sont affichés.
Pour chaque option `--verbose` on diminue de 1 le niveau de severitié à afficher
Pour chaque option `--quiet` on augmente de 1 le niveau de verbosité
Les messages de niveau `PRINT` sont toujours affichés

Enfin d'exécution, la liste des collections utilisées est affichée pour permettre de savoir lesquelles doivent être importées par la commande `ansible-galaxy`. La collection `ansible.builtin` est emabrquée nativment par ansibel. Les collections `beys.vault` et `beys.osiris` sont fournies par défaut dans l'image de CI `ansible-py3`.

### Logs de migration

Quand ils sont affiché dans la console (option `--logs`) ou sauvés dans un fichier (option `--store-logs`), les logs de migration sont au format suivant:

`LIGNE NIVEAU : MESSAGE`
- `LIGNE`: numéro de ligne dans le fichier ou `----` si pas applicable
- `NIVEAU`: le niveau de sévérité du message (PRINT > FATAL > ERROR > WARN > INFO > DEBUG > TRACE)
- `MESSAGE`: le message de la trace
Le nom du fichier analysé/migré est affiché avant ses logs


Exemple:
```
tests/ansible/openjdk/tests/prepare_tests.yml
----- INFO  : Migrating as playbook file
    7 INFO  : module command renamed to ansible.builtin.command
   13 INFO  : module apt_repository renamed to ansible.builtin.apt_repository
   13 WARN  : default value for missing parameter `mode` changed from `420` in version 2.9 to `None` in latest version 
   20 INFO  : module lineinfile renamed to ansible.builtin.lineinfile
   20 WARN  : default value for missing parameter `selevel` changed from `s0` in version 2.9 to `None` in latest version 
tests/ansible/ca-truster/meta/main.yml
----- INFO  : doesn't look like an ansible play or playbook: skipping   
```

Quand ils sont générés en tant que commentaire dans un fichier migré (sauf si l'option `--no-logs-in-files` est spécifiée) il sont au format suivant:

```yaml
# *** MIG ***  <NIVEAU> : <MESSAGE>
```
- `NIVEAU`: le niveau de sévérité du message (PRINT > FATAL > ERROR > WARN > INFO > DEBUG > TRACE)
- `MESSAGE`: le message de la trace

le script essaye de mettre les commentaire au plus près de ce à quoi ils se rapportent

Exemple
```yaml
---
# *** MIG ***  WARNING : There is a breaking change in the facts returned.
# Please check documentation for latest version of module `migration.test.realfacts`
# https://docs.ansible.com/ansible/latest/collections/migration/test/realfacts_module.html
  - name: a simple task
    migration.test.realfacts:
  - name: another one
# *** MIG ***  ERROR : missing parameter `param1` is required in latest version
    migration.test.breaking:
# *** MIG ***  ERROR : unknown module parameter `param2` in latest version
      param2: Don't go breaking my heart

  - name: and a last one
    migration.test.registration:
# *** MIG ***  WARNING : There is a breaking change in the returned values
    register: somevar
```
git
## Exemples d'utilisation

### Génération d'un fichier cache pour une collection

```bash
ansible-migrator.py . -G community.mysql
     599  INFO : Downloading modules for collection community.mysql ...
     599  INFO : Dowloading module 1/7 : mysql_db ...
     599  INFO :   Retrieving doc for module community.mysql.mysql_db ...
    5628  INFO : Dowloading module 2/7 : mysql_info ...
    5628  INFO :   Retrieving doc for module community.mysql.mysql_info ...
    9664  INFO : Dowloading module 3/7 : mysql_query ...
    9664  INFO :   Retrieving doc for module community.mysql.mysql_query ...
   11637  WARN : module community.mysql.mysql_query does not exist in version 2.9
   11637  INFO : Dowloading module 4/7 : mysql_replication ...
   11637  INFO :   Retrieving doc for module community.mysql.mysql_replication ...
   17239  INFO : Dowloading module 5/7 : mysql_role ...
   17239  INFO :   Retrieving doc for module community.mysql.mysql_role ...
   20129  WARN : module community.mysql.mysql_role does not exist in version 2.9
   20129  INFO : Dowloading module 6/7 : mysql_user ...
   20129  INFO :   Retrieving doc for module community.mysql.mysql_user ...
   24127  INFO : Dowloading module 7/7 : mysql_variables ...
   24128  INFO :   Retrieving doc for module community.mysql.mysql_variables ...
   27534  INFO : Saving cache for collection community.mysql ...
```

### Migration d'un fichier fichier playbook

```bash
$ ./ansible_migrator.py -cl tests/ansible/openjdk/tests/prepare_tests.yml 
       0  INFO : Scanning for cache in ./cache ...
      64  INFO : Loading cache from ./cache/beys.vault.cache.yml ...
      75  INFO : Loading cache from ./cache/ansible.builtin.cache.yml ...
     163  INFO : Loading cache from downloaded-modules.cache.yml ...
     174  INFO : 151 modules loaded from cache
     189  INFO : Migrating tests/ansible/openjdk/tests/prepare_tests.yml ...
tests/ansible/openjdk/tests/prepare_tests.yml
----- INFO  : Migrating as playbook file
    7 INFO  : module command renamed to ansible.builtin.command
   13 INFO  : module apt_repository renamed to ansible.builtin.apt_repository
   13 WARN  : default value for missing parameter `mode` changed from `420` in version 2.9 to `None` in latest version 
   20 INFO  : module lineinfile renamed to ansible.builtin.lineinfile
   20 WARN  : default value for missing parameter `selevel` changed from `s0` in version 2.9 to `None` in latest version 
     207  INFO : Used collections: ['ansible.builtin']
     208  INFO : Saving cache ...
     210  INFO : Migration complete
```

### Migration d'un dossier

```bash
 ./ansible_migrator.py -cl tests/ansible/openjdk/tasks
       0  INFO : Scanning for cache in ./cache ...
       0  INFO : Loading cache from ./cache/beys.vault.cache.yml ...
       1  INFO : Loading cache from ./cache/ansible.builtin.cache.yml ...
      78  INFO : Loading cache from downloaded-modules.cache.yml ...
      90  INFO : 74 modules loaded from cache
      93  INFO : Scanning tests/ansible/openjdk/tasks ...
     112  INFO : Migrating tests/ansible/openjdk/tasks/install_bouncy_castle.yml ...
     157  INFO : Migrating tests/ansible/openjdk/tasks/main.yml ...
     184  INFO : Migrating tests/ansible/openjdk/tasks/install_certificate.yml ...
tests/ansible/openjdk/tasks/install_bouncy_castle.yml
----- INFO  : Migrating as play file
    1 INFO  : module stat renamed to ansible.builtin.stat
    6 INFO  : module set_fact renamed to ansible.builtin.set_fact
    6 WARN  : Unknown parameter `java_jre_path`
    6 ERROR : missing parameter `key_value` is required in latest version
   12 INFO  : module get_url renamed to ansible.builtin.get_url
   12 WARN  : default value for missing parameter `selevel` changed from `s0` in version 2.9 to `None` in latest version 
   21 INFO  : module unarchive renamed to ansible.builtin.unarchive
   21 WARN  : default value for missing parameter `exclude` changed from `None` in version 2.9 to `` in latest version 
   21 WARN  : default value for missing parameter `selevel` changed from `s0` in version 2.9 to `None` in latest version 
   30 INFO  : module file renamed to ansible.builtin.file
   30 WARN  : default value for missing parameter `selevel` changed from `s0` in version 2.9 to `None` in latest version 
   39 INFO  : module copy renamed to ansible.builtin.copy
   39 WARN  : default value for missing parameter `selevel` changed from `s0` in version 2.9 to `None` in latest version 
   52 INFO  : module template renamed to ansible.builtin.template
   52 WARN  : default value for missing parameter `selevel` changed from `s0` in version 2.9 to `None` in latest version 
   60 INFO  : module copy renamed to ansible.builtin.copy
   60 WARN  : default value for missing parameter `selevel` changed from `s0` in version 2.9 to `None` in latest version 
   67 INFO  : module command renamed to ansible.builtin.command
   67 WARN  : default value for missing parameter `warn` changed from `yes` in version 2.9 to `no` in latest version 
   76 INFO  : module file renamed to ansible.builtin.file
   76 WARN  : default value for missing parameter `selevel` changed from `s0` in version 2.9 to `None` in latest version 
tests/ansible/openjdk/tasks/main.yml
----- INFO  : Migrating as play file
    2 INFO  : module assert renamed to ansible.builtin.assert
    8 INFO  : module setup renamed to ansible.builtin.setup
    8 WARN  : default value for missing parameter `filter` changed from `*` in version 2.9 to `` in latest version 
   14 INFO  : module package renamed to ansible.builtin.package
   20 INFO  : module include_tasks renamed to ansible.builtin.include_tasks
   20 WARN  : Cannot perform migration checks on free-form parameters
   28 INFO  : module include_tasks renamed to ansible.builtin.include_tasks
   28 WARN  : Cannot perform migration checks on free-form parameters
   36 INFO  : module include_tasks renamed to ansible.builtin.include_tasks
   36 WARN  : Cannot perform migration checks on free-form parameters
   44 INFO  : module include_tasks renamed to ansible.builtin.include_tasks
   44 WARN  : Cannot perform migration checks on free-form parameters
   51 INFO  : module include_tasks renamed to ansible.builtin.include_tasks
   51 WARN  : Cannot perform migration checks on free-form parameters
tests/ansible/openjdk/tasks/install_certificate.yml
----- INFO  : Migrating as play file
    2 INFO  : module set_fact renamed to ansible.builtin.set_fact
    2 WARN  : Unknown parameter `certificate_name`
    2 WARN  : Unknown parameter `certificate_remote_path`
    2 ERROR : missing parameter `key_value` is required in latest version
   10 INFO  : module command renamed to ansible.builtin.command
   10 WARN  : Cannot perform migration checks on free-form parameters
   10 WARN  : There are some breaking changes in the parameters from version 2.9 to latest version
   21 INFO  : module command renamed to ansible.builtin.command
   21 WARN  : Cannot perform migration checks on free-form parameters
   21 WARN  : There are some breaking changes in the parameters from version 2.9 to latest version
   31 INFO  : module copy renamed to ansible.builtin.copy
   31 WARN  : default value for missing parameter `selevel` changed from `s0` in version 2.9 to `None` in latest version 
   42 INFO  : module command renamed to ansible.builtin.command
   42 WARN  : Cannot perform migration checks on free-form parameters
   42 WARN  : There are some breaking changes in the parameters from version 2.9 to latest version
   52 INFO  : module file renamed to ansible.builtin.file
   52 WARN  : default value for missing parameter `selevel` changed from `s0` in version 2.9 to `None` in latest version 
     205  INFO : Used collections: ['ansible.builtin']
     205  INFO : Saving cache ...
     208  INFO : Migration complete
```


## Requirements

Ce script requiert :

- `python 3`

- les librairies suivantes:
  - `lxml`
  - `ruamel.yaml`

```
$ pip install lxml ruamel.yaml
```

## BDD Testing

Assurez-vous que behave est installé

```
$ pip install behave
```

Executez `behave` sur le dossier `bdd`:

```bash
$ behave bdd
```
