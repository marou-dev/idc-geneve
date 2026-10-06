#!/usr/bin/env python3
"""Indice de dépense de chaleur du parc genevois — extraction et contrôle.

Reproduit, depuis la source cantonale ouverte, les chiffres publiés dans
« IDC à Genève : le durcissement de 2027, et qui va le subir »
https://marwanbridi.com/reflexions/idc-geneve-durcissement-2027/

Aucune dépendance : bibliothèque standard uniquement.

    python3 idc_geneve.py extract              # télécharge la couche → idc.csv
    python3 idc_geneve.py analyse              # recalcule tout depuis idc.csv
    python3 idc_geneve.py verify               # compare aux chiffres publiés

⚠️  Le SITG refuse les adresses IP de centre de données. Depuis un serveur, la
    requête échoue sans message explicite — ce qui fait croire à une panne du
    service. Depuis une connexion ordinaire, la couche répond directement.
    Option --proxy pour router via un SOCKS5 (ex. socks5h://127.0.0.1:1080).
"""
import argparse
import csv
import json
import statistics
import sys
import urllib.parse
import urllib.error
import urllib.request

COUCHE = ("https://app2.ge.ch/tergeoservices/rest/services/Hosted"
          "/OCEN_ETAT_IDC_PUBLIC/FeatureServer/0/query")
CHAMPS = ("egid,sre_m2,dernier_idc,annee_dernier_idc,moyenne_3ans,commune")
PAGE = 2000
CSV_DEFAUT = "idc.csv"

# Seuils du reglement sur l'energie, rsGE L 2 30.01, art. 14.
# Al. 1 : seuil d'audit. Al. 2 : depassement significatif, par palier.
# Les deux portent sur l'IDC MOYEN DES 3 DERNIERES ANNEES — c'est ecrit dans
# les deux alineas, et c'est la source d'erreur principale : calculer sur la
# derniere mesure donne un resultat different, et plus eleve.
SEUIL_AUDIT_MJ = 450
PALIERS_MJ = [("jusqu'au 31.12.2026", 800), ("dès le 01.01.2027", 650),
              ("dès le 01.01.2031", 550)]
SRE_PETIT_M2 = 400


def _opener(proxy):
    """SOCKS5 si demande — la bibliotheque standard ne le parle pas, PySocks
    est alors requis. Tout le reste du script tient en stdlib."""
    if not proxy:
        return urllib.request.build_opener()
    if proxy.startswith("socks"):
        try:
            import socks
            from sockshandler import SocksiPyHandler
        except ImportError:
            sys.exit("  SOCKS demandé mais PySocks absent : pip install PySocks\n"
                     "  (ou utilisez un proxy HTTP, pris en charge en stdlib)")
        u = urllib.parse.urlparse(proxy)
        return urllib.request.build_opener(
            SocksiPyHandler(socks.SOCKS5, u.hostname, u.port or 1080, rdns=True))
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy}))


def _get(params, proxy=None):
    params.setdefault("f", "json")
    params.setdefault("returnGeometry", "false")
    url = f"{COUCHE}?{urllib.parse.urlencode(params)}"
    try:
        with _opener(proxy).open(url, timeout=120) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 406:
            sys.exit("  HTTP 406 — le SITG refuse cette adresse IP.\n"
                     "  Mesuré : le refus porte sur l'IP, pas sur l'en-tête — changer\n"
                     "  de User-Agent ne sert à rien. Relancez depuis une connexion\n"
                     "  ordinaire, ou via --proxy socks5h://127.0.0.1:1080.")
        raise


def extract(dest, proxy=None):
    """Pagination complete de la couche. `1=1` et tri par EGID : on prend le
    parc tel que l'office le publie, pas un echantillon."""
    total = _get({"where": "1=1", "returnCountOnly": "true"}, proxy).get("count")
    print(f"  couche annoncée : {total} enregistrements")
    lignes, offset = [], 0
    while True:
        d = _get({"where": "1=1", "outFields": CHAMPS, "orderByFields": "egid",
                  "resultOffset": str(offset), "resultRecordCount": str(PAGE)}, proxy)
        lot = [f["attributes"] for f in d.get("features", [])]
        if not lot:
            break
        lignes += lot
        offset += len(lot)
        print(f"\r  {offset} / {total}", end="", flush=True)
    print()
    champs = CHAMPS.split(",")
    with open(dest, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=champs, extrasaction="ignore")
        w.writeheader()
        w.writerows(lignes)
    print(f"  ✅ {len(lignes)} lignes → {dest}")
    if total is not None and len(lignes) != total:
        print(f"  ⚠ écart avec le compte annoncé ({total}) : vérifier la pagination")
    return lignes


def _lire(src):
    with open(src, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _num(v):
    try:
        x = float(v)
        return x if x > 0 else None
    except (TypeError, ValueError):
        return None


def analyse(src):
    lignes = _lire(src)
    parc = len(lignes)
    dernier = [_num(r["dernier_idc"]) for r in lignes]
    moy3 = [_num(r["moyenne_3ans"]) for r in lignes]

    mesure = [x for x in dernier if x]
    sans = sum(1 for d, m in zip(dernier, moy3) if not d and not m)
    elig = [x for x in moy3 if x]

    res = {
        "parc": parc,
        "sans_mesure": sans,
        "avec_idc": len(mesure),
        "mediane_mj": round(statistics.median(mesure)) if mesure else None,
        "q1_mj": round(statistics.quantiles(mesure, n=4)[0]) if mesure else None,
        "q3_mj": round(statistics.quantiles(mesure, n=4)[2]) if mesure else None,
        "min_mj": round(min(mesure)) if mesure else None,
        "max_mj": round(max(mesure)) if mesure else None,
        "eligibles_moy3": len(elig),
        # Seuil d'audit, al. 1 — sur la moyenne 3 ans, comme le dit le texte
        "audit_moy3": sum(1 for x in elig if x > SEUIL_AUDIT_MJ),
        # et sur la derniere mesure, pour montrer l'ecart que produit l'erreur
        "audit_dernier": sum(1 for x in mesure if x > SEUIL_AUDIT_MJ),
    }
    for libelle, seuil in PALIERS_MJ:
        res[f"palier_{seuil}"] = sum(1 for x in elig if x > seuil)

    # Decoupage par taille — proxy de la maison individuelle / petite copropriete
    petits = [_num(r["moyenne_3ans"]) for r in lignes
              if (_num(r["sre_m2"]) or 0) and _num(r["sre_m2"]) < SRE_PETIT_M2]
    grands = [_num(r["moyenne_3ans"]) for r in lignes
              if (_num(r["sre_m2"]) or 0) >= SRE_PETIT_M2]
    petits = [x for x in petits if x]
    grands = [x for x in grands if x]
    res["petits_n"], res["grands_n"] = len(petits), len(grands)
    res["petits_sup550_pct"] = round(100 * sum(1 for x in petits if x > 550) / len(petits), 1) if petits else None
    res["grands_sup550_pct"] = round(100 * sum(1 for x in grands if x > 550) / len(grands), 1) if grands else None
    return res


def afficher(r):
    p = r["parc"]
    pct = lambda n, d: f"{100*n/d:.1f} %" if d else "—"
    print(f"""
  PARC
    interrogé                      {p:>8}
    sans mesure exploitable        {r['sans_mesure']:>8}   {pct(r['sans_mesure'], p)}
    avec IDC mesuré                {r['avec_idc']:>8}   {pct(r['avec_idc'], p)}
    moyenne 3 ans renseignée       {r['eligibles_moy3']:>8}   {pct(r['eligibles_moy3'], p)}

  DISTRIBUTION de l'IDC mesuré (MJ/m²·an)
    min {r['min_mj']}   Q1 {r['q1_mj']}   médiane {r['mediane_mj']}   Q3 {r['q3_mj']}   max {r['max_mj']}
    ⚠ min et max sont invraisemblables et NE SONT PAS filtrés.
      Médiane et quartiles n'en souffrent pas ; une moyenne serait fausse.

  SEUIL D'AUDIT — art. 14 al. 1, 450 MJ/m²·an
    sur la moyenne 3 ans (texte)   {r['audit_moy3']:>8}   {pct(r['audit_moy3'], r['eligibles_moy3'])} des éligibles
    sur la dernière mesure         {r['audit_dernier']:>8}   {pct(r['audit_dernier'], r['avec_idc'])} des mesurés
    ↑ l'écart entre ces deux lignes est l'erreur de colonne la plus courante

  DÉPASSEMENT SIGNIFICATIF — art. 14 al. 2, sur la moyenne 3 ans""")
    for libelle, seuil in PALIERS_MJ:
        n = r[f"palier_{seuil}"]
        print(f"    {libelle:<22} > {seuil} MJ   {n:>6}   {pct(n, r['eligibles_moy3'])}")
    print(f"""
  PAR TAILLE — séparation à {SRE_PETIT_M2} m² de surface de référence
    petits (n={r['petits_n']})  au-dessus de 550 MJ : {r['petits_sup550_pct']} %
    grands (n={r['grands_n']})  au-dessus de 550 MJ : {r['grands_sup550_pct']} %
""")


# Chiffres publies le 05.10.2026. verify les recalcule et signale tout ecart —
# c'est le but : un chiffre qu'on ne peut pas rejouer n'est pas un resultat.
PUBLIE = {
    "parc": 49734, "sans_mesure": 28677, "avec_idc": 21052,
    "mediane_mj": 386, "q1_mj": 307, "q3_mj": 470,
    "eligibles_moy3": 18668,
    "palier_800": 276, "palier_650": 905, "palier_550": 2377,
    "petits_sup550_pct": 28.4, "grands_sup550_pct": 9.6,
}


def verify(src):
    r = analyse(src)
    print(f"\n  {'grandeur':<24} {'publié':>10} {'recalculé':>12}   état")
    ecarts = 0
    for k, attendu in PUBLIE.items():
        obtenu = r.get(k)
        if obtenu is None:
            etat, ecarts = "ABSENT", ecarts + 1
        elif isinstance(attendu, float):
            ok = abs(obtenu - attendu) <= 0.5
            etat = "ok" if ok else f"ÉCART {obtenu - attendu:+.1f}"
            ecarts += 0 if ok else 1
        else:
            ok = obtenu == attendu
            etat = "ok" if ok else f"ÉCART {obtenu - attendu:+d}"
            ecarts += 0 if ok else 1
        print(f"  {k:<24} {attendu:>10} {obtenu:>12}   {etat}")
    print(f"\n  {ecarts} écart(s). La couche évolue : un écart n'est pas "
          f"forcément une erreur,\n  mais il doit s'expliquer.\n")
    return ecarts


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["extract", "analyse", "verify"])
    ap.add_argument("--csv", default=CSV_DEFAUT)
    ap.add_argument("--proxy", help="SOCKS5 ou HTTP, ex. socks5h://127.0.0.1:1080")
    a = ap.parse_args()
    if a.action == "extract":
        extract(a.csv, a.proxy)
    elif a.action == "analyse":
        afficher(analyse(a.csv))
    else:
        sys.exit(1 if verify(a.csv) else 0)


if __name__ == "__main__":
    main()
