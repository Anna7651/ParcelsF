import xarray as xr

data_xarray = xr.open_zarr("Peninsula.zarr")
#print(data_xarray)

x = data_xarray["lon"].values
y = data_xarray["lat"].values
t = data_xarray["time"].values
t2 = data_xarray["time"].data
t3 = data_xarray["trajectory"].values



print(len(t3))
#print(t2)