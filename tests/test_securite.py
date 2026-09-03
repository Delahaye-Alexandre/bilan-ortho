"""Tests sécurité réseau & configuration (audit 2026-07-17, lot 2).

- C1 : TrustedHostMiddleware — anti DNS rebinding.
- C5 : surcharges de config validées (une chaîne là où un nombre est attendu
  ne doit jamais « briquer » l'application).
- Hôtes LLM/embeddings contraints à la machine locale (RGPD).
- Politique de passphrase à la création du coffre.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app import config, db
from app.main import PASSPHRASE_MIN, app
from tests.conftest import PASSPHRASE

# --- C1 : DNS rebinding -------------------------------------------------------

def test_host_etranger_rejete(client):
    r = client.get("/api/status", headers={"Host": "evil.example.com"})
    assert r.status_code == 400


def test_host_local_accepte(client):
    assert client.get("/api/status", headers={"Host": "localhost"}).status_code == 200
    assert client.get("/api/status", headers={"Host": "127.0.0.1:8000"}).status_code == 200


# --- CSRF : requêtes modifiantes émises depuis une page tierce ----------------

def test_csrf_origine_externe_refusee(client):
    """Le scénario de l'audit 2026-08-11 : un onglet piégé boucle sur
    /api/sauvegarde et remplace tout l'historique par des copies de l'instant.
    L'en-tête Origin est le seul élément que la page tierce ne peut pas mentir."""
    r = client.post("/api/sauvegarde", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert "externe" in r.json()["detail"]


def test_csrf_toutes_les_routes_modifiantes(client):
    """Le contrôle ne dépend d'aucune liste de routes : il porte sur la méthode."""
    externe = {"Origin": "https://evil.example"}
    assert client.post("/api/bilans", json={}, headers=externe).status_code == 403
    assert client.put("/api/config", json={"overrides": {}}, headers=externe).status_code == 403
    assert client.delete("/api/config", headers=externe).status_code == 403
    assert client.post("/api/lock", headers=externe).status_code == 403


def test_csrf_referer_externe_refuse(client):
    """Repli sur Referer quand Origin manque (navigateurs anciens)."""
    r = client.post("/api/sauvegarde", headers={"Referer": "https://evil.example/piege.html"})
    assert r.status_code == 403


def test_csrf_origine_locale_acceptee(client):
    """L'application, servie depuis 127.0.0.1, n'est jamais gênée."""
    for origine in ("http://127.0.0.1:8000", "http://localhost:8000", "http://[::1]:8000"):
        r = client.put("/api/config", json={"overrides": {}}, headers={"Origin": origine})
        assert r.status_code == 200, origine


def test_csrf_lecture_non_bloquee(client):
    """Les requêtes de lecture ne sont pas concernées : la réponse reste
    illisible pour une page tierce (aucun en-tête CORS n'est émis)."""
    r = client.get("/api/status", headers={"Origin": "https://evil.example"})
    assert r.status_code == 200


def test_csrf_sans_en_tete_accepte(client):
    """Un client hors navigateur (script local, test) n'envoie pas d'Origin."""
    assert client.get("/api/status").status_code == 200
    assert client.put("/api/config", json={"overrides": {}}).status_code == 200


# --- C5 : validation des surcharges ------------------------------------------

def test_config_chaine_numerique_coercee(client):
    r = client.put("/api/config", json={
        "overrides": {"rgpd": {"verrouillage_inactivite_minutes": "15"}}
    })
    assert r.status_code == 200
    assert r.json()["rgpd"]["verrouillage_inactivite_minutes"] == 15
    # L'app reste utilisable (avant le correctif : TypeError sur toutes
    # les routes protégées, reset compris).
    assert client.get("/api/patients").status_code == 200


def test_config_valeur_invalide_rejetee(client):
    r = client.put("/api/config", json={
        "overrides": {"rgpd": {"verrouillage_inactivite_minutes": "beaucoup"}}
    })
    assert r.status_code == 422
    assert client.get("/api/patients").status_code == 200


def test_config_cles_inconnues_tolerees(client):
    """Les configurations avancées (clés non modélisées) passent toujours."""
    r = client.put("/api/config", json={
        "overrides": {"llm": {"option_future": True}, "experimental": {"x": 1}}
    })
    assert r.status_code == 200
    assert r.json()["llm"]["option_future"] is True


# --- Hôtes contraints en loopback --------------------------------------------

def test_config_host_distant_refuse(client):
    r = client.put("/api/config", json={
        "overrides": {"llm": {"host": "http://192.0.2.10:11434"}}
    })
    assert r.status_code == 422
    assert "local" in str(r.json()["detail"])
    r = client.put("/api/config", json={
        "overrides": {"embeddings": {"host": "http://exfiltration.example"}}
    })
    assert r.status_code == 422


def test_config_host_local_accepte(client):
    r = client.put("/api/config", json={
        "overrides": {"llm": {"host": "http://127.0.0.1:11434"},
                      "embeddings": {"host": "http://localhost:11434"}}
    })
    assert r.status_code == 200


def test_hote_est_local(monkeypatch):
    """La résolution DNS est simulée : la suite doit rester déterministe et
    strictement hors ligne (un vrai `getaddrinfo` passait hors ligne par
    accident, en échouant — revue 2026-08-11, 9.3)."""
    table = {"mon-poste": ["127.0.0.1"], "ambigu": ["127.0.0.1", "192.0.2.10"]}

    def faux_getaddrinfo(hote, *args, **kwargs):
        if hote not in table:
            raise config.socket.gaierror(-2, f"{hote} : nom inconnu (simulé)")
        return [(None, None, None, None, (ip, 0)) for ip in table[hote]]

    monkeypatch.setattr(config.socket, "getaddrinfo", faux_getaddrinfo)
    assert config.hote_est_local("")
    assert config.hote_est_local("http://127.0.0.1:11434")
    assert config.hote_est_local("http://localhost:11434")
    assert config.hote_est_local("http://[::1]:11434")
    assert config.hote_est_local("http://mon-poste:11434")
    assert not config.hote_est_local("http://192.0.2.10")
    assert not config.hote_est_local("http://exfiltration.example")
    # Un nom qui résout à la fois en local et ailleurs n'est pas local.
    assert not config.hote_est_local("http://ambigu:11434")


# --- Passphrase ---------------------------------------------------------------

def test_passphrase_courte_refusee_a_la_creation(data_dir):
    with TestClient(app, base_url="http://127.0.0.1") as c:
        r = c.post("/api/unlock", json={"passphrase": "court"})
        assert r.status_code == 400
        assert str(PASSPHRASE_MIN) in r.json()["detail"]
        # Une passphrase assez longue crée bien le coffre.
        assert c.post("/api/unlock", json={"passphrase": PASSPHRASE}).status_code == 200


def test_passphrase_courte_acceptee_sur_coffre_existant(data_dir):
    """La politique s'applique à la création : un coffre historique créé avec
    une passphrase courte doit rester ouvrable."""
    con = db.connect(config.db_path(), "court")
    db.init_schema(con)
    con.close()
    with TestClient(app, base_url="http://127.0.0.1") as c:
        assert c.post("/api/unlock", json={"passphrase": "court"}).status_code == 200


# --- Déverrouillage : pas de fuite de connexion -------------------------------

def test_migration_echec_ferme_la_connexion(data_dir, monkeypatch):
    """Si la migration échoue au déverrouillage, la connexion chiffrée doit
    être fermée avant de propager — pas de fuite (BUG-07)."""
    import pytest
    import sqlcipher3

    from app import security
    from tests.conftest import PASSPHRASE as PP

    # Coffre existant : le déverrouillage suivant passera par db.migrate.
    assert security.unlock(PP)
    security.lock()

    ouvertes = []
    vraie_connect = db.connect

    def connect_espionne(path, passphrase):
        con = vraie_connect(path, passphrase)
        ouvertes.append(con)
        return con

    def migration_ko(con):
        raise RuntimeError("migration KO")

    monkeypatch.setattr(db, "connect", connect_espionne)
    monkeypatch.setattr(db, "migrate", migration_ko)
    with pytest.raises(RuntimeError, match="migration KO"):
        security.unlock(PP)
    assert not security.is_unlocked()
    # La connexion ouverte a bien été fermée : tout usage lève ProgrammingError.
    with pytest.raises(sqlcipher3.ProgrammingError):
        ouvertes[-1].execute("SELECT 1")


# --- Restauration guidée des sauvegardes ---------------------------------------

def _coffre_avec_sauvegarde(marqueur_apres: bool = True) -> str:
    """Coffre déverrouillé (sauvegarde auto désactivée pour le déterminisme),
    marqueur « avant », sauvegarde, puis marqueur « apres ». Retourne le nom
    de la sauvegarde."""
    from pathlib import Path

    from app import sauvegarde, security

    assert security.unlock(PASSPHRASE)
    with security.transaction() as con:
        config.ConfigStore(con).set_overrides({"sauvegarde": {"auto_jours": 0}})
        con.execute("INSERT INTO meta(key, value) VALUES('marqueur', 'avant')")
        cfg = config.ConfigStore(con).effective()
        nom = Path(sauvegarde.creer(con, cfg)["fichier"]).name
        if marqueur_apres:
            con.execute("UPDATE meta SET value='apres' WHERE key='marqueur'")
    return nom


def _marqueur() -> str:
    from app import security

    with security.transaction() as con:
        return con.execute("SELECT value FROM meta WHERE key='marqueur'").fetchone()[0]


def test_restauration_remplace_la_base(data_dir):
    """Cycle nominal : la base revient à l'état de la sauvegarde, un filet de
    la base actuelle est créé, l'app est rouverte, l'action est auditée."""
    from app import security

    nom = _coffre_avec_sauvegarde()
    res = security.restaurer(nom, PASSPHRASE)
    assert res["ok"] is True and res["fichier"] == nom
    assert security.is_unlocked()
    assert _marqueur() == "avant"  # les données postérieures ont disparu
    with security.transaction() as con:
        actions = [r[0] for r in con.execute("SELECT action FROM audit_log").fetchall()]
    assert "restauration" in actions
    # filet : la base remplacée reste récupérable depuis le dossier de sauvegarde
    assert res["filet"].startswith("bilan-ortho-sauvegarde-")
    assert (data_dir / "sauvegardes" / res["filet"]).is_file()
    # aucun résidu temporaire à côté de la base
    assert not list(data_dir.glob("bilan.db.restauration.tmp*"))


def test_restauration_passphrase_incorrecte_sans_degat(data_dir):
    """La vérification de la copie précède tout : passphrase KO → erreur
    claire, app TOUJOURS déverrouillée, données intactes, pas de filet."""
    import pytest

    from app import security

    nom = _coffre_avec_sauvegarde()
    avant = sorted(f.name for f in (data_dir / "sauvegardes").iterdir())
    with pytest.raises(security.RestaurationImpossible, match="passphrase"):
        security.restaurer(nom, "mauvaise-passphrase")
    assert security.is_unlocked()
    assert _marqueur() == "apres"
    assert sorted(f.name for f in (data_dir / "sauvegardes").iterdir()) == avant
    assert not list(data_dir.glob("bilan.db.restauration.tmp*"))


def test_restauration_version_future_refusee(data_dir):
    """Une sauvegarde issue d'une version plus récente de l'app ferait échouer
    db.migrate après l'échange : refusée AVANT de toucher la base courante."""
    from pathlib import Path

    import pytest

    from app import security

    nom = _coffre_avec_sauvegarde()
    chemin = data_dir / "sauvegardes" / nom
    copie = db.connect(chemin, PASSPHRASE)
    copie.execute(f"PRAGMA user_version = {db.SCHEMA_VERSION + 1}")
    copie.commit()
    copie.close()
    for suffixe in ("-wal", "-shm"):
        Path(str(chemin) + suffixe).unlink(missing_ok=True)
    with pytest.raises(security.RestaurationImpossible, match="plus récente"):
        security.restaurer(nom, PASSPHRASE)
    assert security.is_unlocked()
    assert _marqueur() == "apres"


def test_restauration_echec_echange_base_reouverte(data_dir, monkeypatch):
    """Si l'échange atomique échoue, l'ancienne base est intacte et ROUVERTE
    (pas d'app laissée verrouillée sur un demi-échec)."""
    import os as os_mod

    import pytest

    from app import security

    nom = _coffre_avec_sauvegarde()

    vrai_replace = os_mod.replace

    def replace_ko(src, dst):
        # Ne fait échouer QUE l'échange final vers bilan.db : le os.replace
        # du filet (sauvegarde.creer) doit continuer de fonctionner.
        if str(dst) == str(config.db_path()):
            raise OSError("échange KO")
        return vrai_replace(src, dst)

    monkeypatch.setattr(os_mod, "replace", replace_ko)
    with pytest.raises(RuntimeError, match="intactes"):
        security.restaurer(nom, PASSPHRASE)
    assert security.is_unlocked()
    assert _marqueur() == "apres"
    assert not list(data_dir.glob("bilan.db.restauration.tmp*"))


def test_restauration_sidecars_residuels_purges(data_dir, monkeypatch):
    """Des -wal/-shm orphelins (arrêt brutal) sont purgés avant l'échange :
    un vieux journal rejoué à côté de la base restaurée la corromprait."""
    from pathlib import Path

    from app import security

    nom = _coffre_avec_sauvegarde()

    vrai_lock = security.lock

    def lock_puis_orphelins():
        vrai_lock()
        Path(str(config.db_path()) + "-wal").write_bytes(b"journal orphelin")
        Path(str(config.db_path()) + "-shm").write_bytes(b"index orphelin")

    monkeypatch.setattr(security, "lock", lock_puis_orphelins)
    res = security.restaurer(nom, PASSPHRASE)
    assert res["ok"] is True
    assert security.is_unlocked()
    assert _marqueur() == "avant"
    # Les orphelins factices n'ont pas survécu : si le faux -wal avait été
    # laissé à côté de la base restaurée, la réouverture aurait tenté de le
    # rejouer et la lecture échouerait.
    with security.transaction() as con:
        assert con.execute("SELECT count(*) FROM sqlite_master").fetchone()[0] > 0


# --- Verrouillage automatique ACTIF (revue 2026-08-11, 5.3) -----------------

def test_verrouillage_inactivite_sans_aucune_requete(data_dir, monkeypatch):
    """Sans requête, `enforce_inactivity()` n'était jamais appelé : un coffre
    « verrouillé après 15 min » restait ouvert indéfiniment (portable en
    veille). Le minuteur serveur doit verrouiller tout seul."""
    import time

    from app import security

    monkeypatch.setattr(security, "_MINUTEUR_INTERVALLE_S", 0.05)
    assert security.unlock(PASSPHRASE)
    assert security._state["minuteur"] is not None
    # Dernière activité simulée il y a un jour (délai par défaut : 15 min).
    with security._lock:
        security._state["last_activity"] = time.monotonic() - 86400
    limite = time.monotonic() + 3
    while security.is_unlocked() and time.monotonic() < limite:
        time.sleep(0.02)
    assert not security.is_unlocked()
    assert security._state["minuteur"] is None


def test_verrouillage_manuel_desarme_le_minuteur(data_dir, monkeypatch):
    import time

    from app import security

    monkeypatch.setattr(security, "_MINUTEUR_INTERVALLE_S", 0.05)
    assert security.unlock(PASSPHRASE)
    security.lock()
    assert security._state["minuteur"] is None
    time.sleep(0.15)  # aucun tic tardif ne doit rouvrir quoi que ce soit ni planter
    assert not security.is_unlocked()
    # Un coffre actif (activité récente) n'est pas verrouillé par le minuteur.
    assert security.unlock(PASSPHRASE)
    time.sleep(0.15)
    assert security.is_unlocked()
    security.lock()


# --- Passphrase prévisible et mémoire chiffrée (revue 2026-08-11, 5.6) -------

def test_passphrase_faible_raisons():
    from app import security

    assert security.passphrase_faible("motdepasse12") == (
        "trop prévisible (un mot courant suivi de chiffres ou de signes)"
    )
    assert security.passphrase_faible("mot de passe 26").startswith("trop prévisible")
    assert security.passphrase_faible("AZERTYUIOP!?1").startswith("trop prévisible")
    assert security.passphrase_faible("111111111111") == "trop répétitive"
    assert security.passphrase_faible("123456789012") == "composée uniquement de chiffres"
    # Une phrase de plusieurs mots, ou un mot courant noyé dans autre chose : ok.
    assert security.passphrase_faible("les hérons volent bas ce soir") == ""
    assert security.passphrase_faible("motdepasse-du-cabinet-2026") == ""
    assert security.passphrase_faible(PASSPHRASE) == ""


def test_passphrase_previsible_refusee_a_la_creation(data_dir):
    """« motdepasse12 » passait la longueur minimale. Une copie du coffre
    s'attaque hors ligne sans limite d'essais : le message le dit."""
    with TestClient(app, base_url="http://127.0.0.1") as c:
        for p in ("motdepasse12", "azertyuiop123", "111111111111", "123456789012"):
            r = c.post("/api/unlock", json={"passphrase": p})
            assert r.status_code == 400, p
            assert "hors ligne" in r.json()["detail"], p
        assert c.post("/api/unlock", json={"passphrase": PASSPHRASE}).status_code == 200


def test_passphrase_previsible_acceptee_sur_coffre_existant(data_dir):
    """Comme la longueur : la règle vaut à la création, jamais à l'ouverture
    d'un coffre historique."""
    from app import security

    assert security.unlock("motdepasse12")  # coffre créé sans passer par l'API
    security.lock()
    with TestClient(app, base_url="http://127.0.0.1") as c:
        assert c.post("/api/unlock", json={"passphrase": "motdepasse12"}).status_code == 200


def test_memoire_des_pages_dechiffrees_effacee(con):
    """cipher_memory_security est désactivé par défaut dans cette distribution
    de SQLCipher : la clé dérivée pouvait partir en swap ou en hibernation."""
    assert str(con.execute("PRAGMA cipher_memory_security").fetchone()[0]) == "1"
