from pytest import approx

from radar.scoring import puntaje, puntaje_ganga


def test_puntaje():
    assert puntaje(0.30, 5, 5, False, [], None) == approx(0.30)
    assert puntaje(0.30, 5, 5, False, ["must sell"], 45) == approx(0.39)
    assert puntaje(0.30, 5, 0, False, [], None) == 0
    assert puntaje(-0.1, 5, 5, False, [], None) == 0
    assert puntaje(0.30, 5, 0, True, [], None) == approx(0.30)


def test_puntaje_ganga():
    assert puntaje_ganga(0.55, 5, [], None) == approx(0.55)
    assert puntaje_ganga(0.55, 2, [], None) == approx(0.22)
