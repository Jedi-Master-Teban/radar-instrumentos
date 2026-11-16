from datetime import date

from radar.montaje import ciudades_de_hoy

C = ["miami", "orlando", "tampa", "nyc", "la", "chicago"]


def test_rotacion_cubre_todas_las_ciudades():
    vistas = set()
    for d in range(3):
        hoy = date(2026, 11, 15 + d)
        bloque = ciudades_de_hoy(C, 2, hoy)
        assert len(bloque) == 2
        vistas.update(bloque)
    assert vistas == set(C)


def test_rotacion_limites():
    assert ciudades_de_hoy([], 4, date(2026, 11, 15)) == []
    assert sorted(ciudades_de_hoy(C, 99, date(2026, 11, 15))) == sorted(C)
    assert len(ciudades_de_hoy(C, 0, date(2026, 11, 15))) == 1
