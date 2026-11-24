import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


def _article(url, title, summary="", source="MundoDeportivo-Balonmano"):
    return {"url": url, "title_orig": title, "title": title,
            "summary": summary, "source_name": source}


def test_other_sport_article_is_skipped():
    from run_all import _should_skip_article
    assert _should_skip_article(_article(
        "https://www.mundodeportivo.com/ciclismo/20261118/1004252729/impactante-fichaje-primoz-roglic.html",
        'Impactante fichaje de Primoz Roglic: "Siento que la conexión es perfecta"'))


def test_handball_article_under_another_sport_path_is_kept():
    # En Mundo Deportivo el balonmano del Barça vive en /futbol/fc-barcelona/,
    # y los artículos de balonmano de eixdiari.cat en /esports/ ("deportes").
    from run_all import _should_skip_article
    assert not _should_skip_article(_article(
        "https://www.mundodeportivo.com/baloncesto/20261118/1/polideportivo.html",
        "El Barça de balonmano celebra su décimo doblete"))
    assert not _should_skip_article(_article(
        "https://www.eixdiari.cat/esports/doc/122319/subcampiones-despanya",
        "Subcampiones d'Espanya", "L'equip d'handbol del Ribes", "EixDiari-handbol"))


def test_babyhand_promo_is_skipped():
    from run_all import _should_skip_article
    assert _should_skip_article(_article(
        "https://www.ffhandball.fr/actualite/lactualite-du-hand/mois-du-babyhand-lart-de-bouger-ensemble/",
        "MOIS DU BABYHAND : L’ART DE BOUGER ENSEMBLE", source="FFHandball-fed"))
    # El minihandball sí tiene torneos con crónica: no se filtra.
    assert not _should_skip_article(_article(
        "https://www.ffhandball.fr/actualite/finale-minihand/",
        "Finale du tournoi national de minihand", source="FFHandball-fed"))
