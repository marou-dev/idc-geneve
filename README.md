# IDC Genève — reproduire les chiffres

Extraction et recalcul, depuis la source cantonale ouverte, des chiffres publiés
dans **[IDC à Genève : le durcissement de 2027, et qui va le subir](https://marwanbridi.com/reflexions/idc-geneve-durcissement-2027/)**.

Le but n'est pas de montrer du code. Il est de rendre ces chiffres **contestables** :
un résultat qu'on ne peut pas rejouer n'est pas un résultat, c'est une opinion chiffrée.

```bash
python3 idc_geneve.py extract    # télécharge la couche publique → idc.csv
python3 idc_geneve.py analyse    # recalcule tout depuis le CSV
python3 idc_geneve.py verify     # compare aux chiffres publiés, signale les écarts
```

Bibliothèque standard uniquement. `PySocks` n'est nécessaire que si vous passez
par un proxy SOCKS — voir *Accès* ci-dessous.

## La source

Couche **`OCEN_ETAT_IDC_PUBLIC`** du [SITG](https://ge.ch/sitg), service de
requête de l'État de Genève. Interrogée en lecture seule, pagination complète
(`where=1=1`, tri par EGID, pages de 2 000) : on prend le parc tel que l'office
le publie, pas un échantillon.

Champs retenus : `egid`, `sre_m2`, `dernier_idc`, `annee_dernier_idc`,
`moyenne_3ans`, `commune`.

## La règle appliquée

Règlement d'application de la loi sur l'énergie, **rsGE L 2 30.01, art. 14** :

| | Seuil | Porte sur |
|---|---|---|
| al. 1 — seuil d'audit | 450 MJ/m²·an (125 kWh) | **IDC moyen des 3 dernières années** |
| al. 2 — dépassement significatif, jusqu'au 31.12.2026 | 800 MJ (222 kWh) | **idem** |
| al. 2 — dès le 01.01.2027 | 650 MJ (180 kWh) | **idem** |
| al. 2 — dès le 01.01.2031 | 550 MJ (153 kWh) | **idem** |

**Les deux alinéas portent sur la moyenne triennale, pas sur la dernière mesure.**
C'est l'erreur de colonne la plus coûteuse : `analyse` affiche délibérément les
deux comptes côte à côte pour que l'écart soit visible.

## Ce que le script ne fait pas

**Il ne filtre pas les valeurs aberrantes.** La couche contient des valeurs
invraisemblables aux deux extrémités. Médiane et quartiles n'en souffrent pas ;
une moyenne serait fausse, elle n'est donc affichée nulle part.

**Il ne distingue pas « non assujetti » de « non déclaré ».** Un enregistrement
est compté « sans mesure exploitable » lorsque `dernier_idc` *et* `moyenne_3ans`
sont absents ou nuls. La donnée publique ne permet pas d'aller plus loin.

**Il ne valide pas le proxy de taille.** La séparation à 400 m² de surface de
référence énergétique sert d'approximation pour la maison individuelle ou la
petite copropriété. Cette approximation a été testée séparément contre le
registre fédéral des bâtiments, sur un échantillon non aléatoire de 706
bâtiments : elle indique une tendance, pas un taux.

**Il ne suit rien dans le temps.** La couche ne conserve qu'un enregistrement
par bâtiment — le dernier indice connu, jamais une série. Un bâtiment dont la
mesure date de 2012 n'est pas un bâtiment mesuré en 2012 : c'est un bâtiment
qu'on ne mesure plus. Les deux se ressemblent dans un tableau et ne disent pas
la même chose.

## Accès — l'obstacle qu'on ne voit pas venir

**Le SITG refuse les adresses IP de centre de données.** La requête renvoie un
`HTTP 406 Not Acceptable`, sans message explicatif : on croit à une panne du
service ou à une URL fausse.

Mesuré le 06.10.2026 : le refus porte sur **l'IP**, pas sur l'en-tête. Trois
`User-Agent` différents — `Python-urllib`, un navigateur, `curl` — reçoivent
tous un 406 depuis la même machine, pendant que la même requête aboutit par une
sortie résidentielle. Changer de `User-Agent` ne sert à rien.

Depuis une connexion ordinaire, la couche répond directement. Sinon :

```bash
pip install PySocks
python3 idc_geneve.py extract --proxy socks5h://127.0.0.1:1080
```

## Portée

Données publiques cantonales uniquement. Aucune donnée d'employeur, de client ou
de tiers n'entre dans ce dépôt, et le CSV produit n'est pas versionné : il se
régénère.

## Licence

MIT pour le code. Les données appartiennent à l'État de Genève et restent
soumises aux [conditions du SITG](https://ge.ch/sitg/sitg_catalog/conditions).
