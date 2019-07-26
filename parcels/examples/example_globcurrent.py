from datetime import timedelta as delta
from glob import glob
from os import path

import numpy as np
import pytest
import xarray as xr

from parcels import AdvectionRK4
from parcels import ErrorCode
from parcels import FieldSet
from parcels import JITParticle
from parcels import ParticleSet
from parcels import ScipyParticle
from parcels import Variable


ptype = {'scipy': ScipyParticle, 'jit': JITParticle}


def set_globcurrent_fieldset(filename=None, indices=None, deferred_load=True, use_xarray=False, time_periodic=False, timestamps=None):
    if filename is None:
        filename = path.join(path.dirname(__file__), 'GlobCurrent_example_data',
                             '2002*-GLOBCURRENT-L4-CUReul_hs-ALT_SUM-v02.0-fv01.0.nc')
    variables = {'U': 'eastward_eulerian_current_velocity', 'V': 'northward_eulerian_current_velocity'}
    if timestamps is None:
        dimensions = {'lat': 'lat', 'lon': 'lon', 'time': 'time'}
    else:
        dimensions = {'lat': 'lat', 'lon': 'lon'}
    if use_xarray:
        ds = xr.open_mfdataset(filename)
        return FieldSet.from_xarray_dataset(ds, variables, dimensions, indices, deferred_load=deferred_load, time_periodic=time_periodic)
    else:
        return FieldSet.from_netcdf(filename, variables, dimensions, indices, deferred_load=deferred_load, time_periodic=time_periodic, timestamps=timestamps)


@pytest.mark.parametrize('use_xarray', [True, False])
def test_globcurrent_fieldset(use_xarray):
    fieldset = set_globcurrent_fieldset(use_xarray=use_xarray)
    assert(fieldset.U.lon.size == 81)
    assert(fieldset.U.lat.size == 41)
    assert(fieldset.V.lon.size == 81)
    assert(fieldset.V.lat.size == 41)

    indices = {'lon': [5], 'lat': range(20, 30)}
    fieldsetsub = set_globcurrent_fieldset(indices=indices, use_xarray=use_xarray)
    assert np.allclose(fieldsetsub.U.lon, fieldset.U.lon[indices['lon']])
    assert np.allclose(fieldsetsub.U.lat, fieldset.U.lat[indices['lat']])
    assert np.allclose(fieldsetsub.V.lon, fieldset.V.lon[indices['lon']])
    assert np.allclose(fieldsetsub.V.lat, fieldset.V.lat[indices['lat']])


@pytest.mark.parametrize('mode', ['scipy', 'jit'])
@pytest.mark.parametrize('dt, lonstart, latstart', [(3600., 25, -35), (-3600., 20, -39)])
@pytest.mark.parametrize('use_xarray', [True, False])
def test_globcurrent_fieldset_advancetime(mode, dt, lonstart, latstart, use_xarray):
    basepath = path.join(path.dirname(__file__), 'GlobCurrent_example_data',
                         '20*-GLOBCURRENT-L4-CUReul_hs-ALT_SUM-v02.0-fv01.0.nc')
    files = sorted(glob(str(basepath)))

    fieldsetsub = set_globcurrent_fieldset(files[0:10], use_xarray=use_xarray)
    psetsub = ParticleSet.from_list(fieldset=fieldsetsub, pclass=ptype[mode], lon=[lonstart], lat=[latstart])

    fieldsetall = set_globcurrent_fieldset(files[0:10], deferred_load=False, use_xarray=use_xarray)
    psetall = ParticleSet.from_list(fieldset=fieldsetall, pclass=ptype[mode], lon=[lonstart], lat=[latstart])
    if dt < 0:
        psetsub.time[0] = fieldsetsub.U.grid.time[-1]
        psetall.time[0] = fieldsetall.U.grid.time[-1]

    psetsub.execute(AdvectionRK4, runtime=delta(days=7), dt=dt)
    psetall.execute(AdvectionRK4, runtime=delta(days=7), dt=dt)

    assert abs(psetsub.lon[0] - psetall.lon[0]) < 1e-4


@pytest.mark.parametrize('mode', ['scipy', 'jit'])
@pytest.mark.parametrize('use_xarray', [True, False])
def test_globcurrent_particles(mode, use_xarray):
    fieldset = set_globcurrent_fieldset(use_xarray=use_xarray)

    lonstart = [25]
    latstart = [-35]

    pset = ParticleSet(fieldset, pclass=ptype[mode], lon=lonstart, lat=latstart)

    pset.execute(AdvectionRK4, runtime=delta(days=1), dt=delta(minutes=5))

    assert(abs(pset.lon[0] - 23.8) < 1)
    assert(abs(pset.lat[0] - -35.3) < 1)


@pytest.mark.parametrize('mode', ['scipy', 'jit'])
@pytest.mark.parametrize('rundays', [300, 900])
def test_globcurrent_time_periodic(mode, rundays):
    sample_var = []
    for deferred_load in [True, False]:
        fieldset = set_globcurrent_fieldset(time_periodic=delta(days=365), deferred_load=deferred_load)

        class MyParticle(ptype[mode]):
            sample_var = Variable('sample_var', initial=fieldset.U)

        pset = ParticleSet(fieldset, pclass=MyParticle, lon=25, lat=-35, time=fieldset.U.grid.time[0])

        def SampleU(particle, fieldset, time):
            particle.sample_var += fieldset.U[time, particle.depth, particle.lat, particle.lon]

        pset.execute(SampleU, runtime=delta(days=rundays), dt=delta(days=1))
        sample_var.append(pset.sample_var[0])

    assert np.allclose(sample_var[0], sample_var[1])


@pytest.mark.parametrize('dt', [-300, 300])
def test_globcurrent_xarray_vs_netcdf(dt):
    fieldsetNetcdf = set_globcurrent_fieldset(use_xarray=False)
    fieldsetxarray = set_globcurrent_fieldset(use_xarray=True)
    lonstart, latstart, runtime = (25, -35, delta(days=7))

    psetN = ParticleSet(fieldsetNetcdf, pclass=JITParticle, lon=lonstart, lat=latstart)
    psetN.execute(AdvectionRK4, runtime=runtime, dt=dt)

    psetX = ParticleSet(fieldsetxarray, pclass=JITParticle, lon=lonstart, lat=latstart)
    psetX.execute(AdvectionRK4, runtime=runtime, dt=dt)

    assert np.allclose(psetN.lon[0], psetX.lon[0])
    assert np.allclose(psetN.lat[0], psetX.lat[0])


@pytest.mark.parametrize('dt', [-300, 300])
def test_globcurrent_netcdf_timestamps(dt):
    fieldsetNetcdf = set_globcurrent_fieldset()
    timestamps = fieldsetNetcdf.U.grid.timeslices
    fieldsetTimestamps = set_globcurrent_fieldset(timestamps=timestamps)
    lonstart, latstart, runtime = (25, -35, delta(days=7))

    psetN = ParticleSet(fieldsetNetcdf, pclass=JITParticle, lon=lonstart, lat=latstart)
    psetN.execute(AdvectionRK4, runtime=runtime, dt=dt)

    psetT = ParticleSet(fieldsetTimestamps, pclass=JITParticle, lon=lonstart, lat=latstart)
    psetT.execute(AdvectionRK4, runtime=runtime, dt=dt)

    assert np.allclose(psetN.lon[0], psetT.lon[0])
    assert np.allclose(psetN.lat[0], psetT.lat[0])


def test__particles_init_time():
    fieldset = set_globcurrent_fieldset()

    lonstart = [25]
    latstart = [-35]

    # tests the different ways of initialising the time of a particle
    pset = ParticleSet(fieldset, pclass=JITParticle, lon=lonstart, lat=latstart, time=np.datetime64('2002-01-15'))
    pset2 = ParticleSet(fieldset, pclass=JITParticle, lon=lonstart, lat=latstart, time=14*86400)
    pset3 = ParticleSet(fieldset, pclass=JITParticle, lon=lonstart, lat=latstart, time=np.array([np.datetime64('2002-01-15')]))
    pset4 = ParticleSet(fieldset, pclass=JITParticle, lon=lonstart, lat=latstart, time=[np.datetime64('2002-01-15')])
    assert pset.time[0] - pset2.time[0] == 0
    assert pset.time[0] - pset3.time[0] == 0
    assert pset.time[0] - pset4.time[0] == 0


@pytest.mark.xfail(reason="Time extrapolation error expected to be thrown", strict=True)
@pytest.mark.parametrize('mode', ['scipy', 'jit'])
@pytest.mark.parametrize('use_xarray', [True, False])
def test_globcurrent_time_extrapolation_error(mode, use_xarray):
    fieldset = set_globcurrent_fieldset(use_xarray=use_xarray)

    pset = ParticleSet(fieldset, pclass=ptype[mode], lon=[25], lat=[-35],
                       time=fieldset.U.time[0]-delta(days=1).total_seconds())

    pset.execute(AdvectionRK4, runtime=delta(days=1), dt=delta(minutes=5))


@pytest.mark.parametrize('mode', ['scipy', 'jit'])
@pytest.mark.parametrize('use_xarray', [True, False])
def test_globcurrent_dt0(mode, use_xarray):
    fieldset = set_globcurrent_fieldset(use_xarray=use_xarray)
    pset = ParticleSet(fieldset, pclass=ptype[mode], lon=[25], lat=[-35])
    pset.execute(AdvectionRK4, dt=0.)


@pytest.mark.parametrize('mode', ['scipy', 'jit'])
@pytest.mark.parametrize('dt', [-300, 300])
@pytest.mark.parametrize('use_xarray', [True, False])
def test_globcurrent_variable_fromfield(mode, dt, use_xarray):
    fieldset = set_globcurrent_fieldset(use_xarray=use_xarray)

    class MyParticle(ptype[mode]):
        sample_var = Variable('sample_var', initial=fieldset.U)
    time = fieldset.U.grid.time[0] if dt > 0 else fieldset.U.grid.time[-1]
    pset = ParticleSet(fieldset, pclass=MyParticle, lon=[25], lat=[-35], time=time)

    pset.execute(AdvectionRK4, runtime=delta(days=1), dt=dt)


@pytest.mark.parametrize('mode', ['scipy', 'jit'])
def test_globcurrent_particle_independence(mode, rundays=5):
    fieldset = set_globcurrent_fieldset()
    time0 = fieldset.U.grid.time[0]

    def DeleteP0(particle, fieldset, time):
        if particle.id == 0:
            return ErrorCode.ErrorOutOfBounds  # we want to pass through recov loop

    def DeleteParticle(particle, fieldset, time):
        particle.delete()

    pset0 = ParticleSet(fieldset, pclass=JITParticle,
                        lon=[25, 25],
                        lat=[-35, -35],
                        time=time0)

    pset0.execute(pset0.Kernel(DeleteP0)+AdvectionRK4,
                  runtime=delta(days=rundays),
                  dt=delta(minutes=5),
                  recovery={ErrorCode.ErrorOutOfBounds: DeleteParticle})

    pset1 = ParticleSet(fieldset, pclass=JITParticle,
                        lon=[25, 25],
                        lat=[-35, -35],
                        time=time0)

    pset1.execute(AdvectionRK4,
                  runtime=delta(days=rundays),
                  dt=delta(minutes=5))

    assert np.allclose([pset0.lon[-1], pset0.lat[-1]], [pset1.lon[-1], pset1.lat[-1]])
