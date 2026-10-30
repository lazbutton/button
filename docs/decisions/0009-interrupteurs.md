# 0009 · Une fonction risquée a un interrupteur

Acceptée, octobre 2026.

## Contexte

La console et le moteur arrivent sur une station en service. Une fonction nouvelle qui gêne l'antenne doit pouvoir se couper tout de suite, sans redéployer ni revenir à une version plus ancienne.

## Décision

- Une fonction nouvelle et risquée se coupe par une clé de la table `settings` du moteur (modèle `Setting`).
- Une clé absente garde le comportement par défaut, choisi pour ne rien casser.
- Les clés nouvelles s'appellent `features.<nom>`. Le modèle à suivre est `agenda_enabled`, dans `engine/radiotomate/services/agenda.py`.
- Une clé qui contient un point devient un sous-dictionnaire, mêlé à la configuration YAML. Son préfixe ne doit pas exister dans le YAML.

## Conséquences

- Chaque interrupteur a un test fonction coupée et un test fonction allumée.
- L'écran qui change un interrupteur est réservé aux admins.
