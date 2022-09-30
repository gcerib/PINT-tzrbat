""" Test for pint solar wind module
"""

import os
from io import StringIO
import pytest
import numpy as np
from numpy.testing import assert_allclose
import copy
import sys

import astropy.units as u
from astropy.time import Time
from pint.models import get_model, get_model_and_toas
from pint.fitter import Fitter
from pint.toa import get_TOAs
from pint.simulation import make_fake_toas_uniform
from pint.models.solar_wind_dispersion import SolarWindDispersionX
from pinttestdata import datadir


par = """
PSR J1234+5678
F0 1
DM 10
ELAT 0
ELONG 0
PEPOCH 54000
"""

march_equinox = Time("2015-03-20 22:45:00").mjd
year = 365.25  # in mjd


@pytest.mark.parametrize("frac", [0, 0.25, 0.5, 0.123])
def test_sun_angle_ecliptic(frac):
    model = get_model(StringIO(par))
    toas = make_fake_toas_uniform(
        march_equinox, march_equinox + 2 * year, 10, model=model, obs="gbt"
    )
    # Sun longitude, from Astronomical Almanac
    sun_n = toas.get_mjds().value - 51544.5
    sun_L = 280.460 + 0.9856474 * sun_n
    sun_g = 357.528 + 0.9856003 * sun_n
    sun_longitude = (
        sun_L
        + 1.915 * np.sin(np.deg2rad(sun_g))
        + 0.020 * np.sin(2 * np.deg2rad(sun_g))
    )
    sun_longitude = (sun_longitude + 180) % 360 - 180
    angles = np.rad2deg(model.sun_angle(toas).value)
    assert_allclose(angles, np.abs(sun_longitude), atol=1)


def test_solar_wind_delays_positive():
    model = get_model(StringIO("\n".join([par, "NE_SW 1"])))
    toas = make_fake_toas_uniform(54000, 54000 + year, 13, model=model, obs="gbt")
    assert np.all(model.components["SolarWindDispersion"].solar_wind_dm(toas) > 0)


def test_solar_wind_generalmodel():
    # default model
    model = get_model(StringIO("\n".join([par, "NE_SW 1"])))
    # model with general power-law index
    model2 = get_model(StringIO("\n".join([par, "NE_SW 1\nSWM 1"])))
    toas = make_fake_toas_uniform(54000, 54000 + year, 13, model=model, obs="gbt")

    assert np.allclose(
        model2.components["SolarWindDispersion"].solar_wind_delay(toas),
        model.components["SolarWindDispersion"].solar_wind_delay(toas),
    )


def test_solar_wind_generalmodel_deriv():
    # default model
    model = get_model(StringIO("\n".join([par, "NE_SW 1"])))
    # model with general power-law index but the default is p==2 (same as SWM==0)
    model2 = get_model(StringIO("\n".join([par, "NE_SW 1\nSWM 1"])))
    toas = make_fake_toas_uniform(54000, 54000 + year, 13, model=model, obs="gbt")

    assert np.allclose(
        model2.components["SolarWindDispersion"].d_dm_d_ne_sw(toas, "NE_SW").to(u.cm),
        model.components["SolarWindDispersion"].d_dm_d_ne_sw(toas, "NE_SW").to(u.cm),
    )


def test_solar_wind_swm2():
    # should fail for SWM != 0 or 1
    model = get_model(StringIO("\n".join([par, "NE_SW 1\nSWM 2"])))
    with pytest.raises(NotImplementedError):
        toas = make_fake_toas_uniform(54000, 54000 + year, 13, model=model, obs="gbt")


def test_solar_wind_generalmodel_p1():
    # model with general power-law index
    model = get_model(StringIO("\n".join([par, "NE_SW 1\nSWM 1\nSWP 1"])))
    with pytest.raises(NotImplementedError):
        toas = make_fake_toas_uniform(54000, 54000 + year, 13, model=model, obs="gbt")


def test_swx():
    # default model
    model = get_model(StringIO("\n".join([par, "NE_SW 1"])))
    # SWX model with a single segment to match the default model
    model2 = get_model(
        StringIO(
            "\n".join(
                [par, "SWX_0001 1\nSWXP_0001 2\nSWXR1_0001 53999\nSWXR2_0001 55000"]
            )
        )
    )
    toas = make_fake_toas_uniform(54000, 54000 + year, 13, model=model, obs="gbt")
    assert np.allclose(model2.swx_dm(toas), model.solar_wind_dm(toas))
    assert np.allclose(model2.swx_delay(toas), model.solar_wind_delay(toas))
    assert np.allclose(
        model2.d_dm_d_param(toas, "SWX_0001"), model.d_dm_d_param(toas, "NE_SW")
    )
    assert np.allclose(
        model2.d_delay_d_param(toas, "SWX_0001"), model.d_delay_d_param(toas, "NE_SW")
    )


def test_swfits():
    # default model and TOAs
    model0, t = get_model_and_toas(
        os.path.join(datadir, "2145_swfit.par"), os.path.join(datadir, "2145_swfit.tim")
    )
    # default SWM=0 model
    model1 = copy.deepcopy(model0)
    model1.SWM.value = 0
    # SWM=1 model with p=2
    model2 = copy.deepcopy(model0)
    model2.SWM.value = 1
    model2.SWP.value = 2
    # SWX model
    model3 = copy.deepcopy(model0)
    model3.add_component(SolarWindDispersionX())
    model3.remove_component("SolarWindDispersion")
    model3.SWXR1_0001.value = t.get_mjds().min().value
    model3.SWXR2_0001.value = t.get_mjds().max().value
    model3.SWXP_0001.value = 2
    model3.SWX_0001.value = 10

    f1 = Fitter.auto(t, model1)
    f2 = Fitter.auto(t, model2)
    f3 = Fitter.auto(t, model3)

    f1.fit_toas()
    f2.fit_toas()
    f3.fit_toas()
    assert np.isclose(f1.model.NE_SW.value, f2.model.NE_SW.value)
    assert np.isclose(f1.model.NE_SW.value, f3.model.SWX_0001.value)
