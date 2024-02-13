import os
import hydrodataset as hds
from hydrodataset import HydroDataset, CACHE_DIR
from hydrodataset.camels import map_string_vars
import numpy as np
from netCDF4 import Dataset as ncdataset
import collections
import pandas as pd
import xarray as xr

MEAN_NO_DATASET_ERROR_LOG = (
    "We cannot read this dataset now. Please check if you choose correctly:\n"
)

class MEAN(HydroDataset):
    def __init__(
        self,
        data_path=os.path.join("lstm_data","mean"),
        download=False,
        region: str = "US",
    ):
        super().__init__(data_path)
        self.region = region
        self.data_source_description = self.set_data_source_describe()
        if download:
            raise NotImplementedError(
                "We don't provide methods for downloading data at present\n"
            )
        self.sites = self.read_site_info()
    """
        Initialization for CAMELS series dataset

        Parameters
        ----------
        data_path
            where we put the dataset.
            we already set the ROOT directory for hydrodataset,
            so here just set it as a relative path,
            by default "camels/camels_us"
        download
            if true, download, by defaulf False
        region
            the default is CAMELS(-US), since it's the first CAMELS dataset.
            All are included in CAMELS_REGIONS
    """

    def get_name(self):
        return "MEAN_" + self.region

    def set_data_source_describe(self) -> collections.OrderedDict:
        """
        the files in the dataset and their location in file system

        Returns
        -------
        collections.OrderedDict
            the description for GPM and GFS dataset
        """
        mean_db = self.data_source_dir
        if self.region == "US":
            return self._set_data_source_MeanUS_describe(mean_db)
        else:
            raise NotImplementedError(MEAN_NO_DATASET_ERROR_LOG)

    def _set_data_source_MeanUS_describe(self, mean_db):
        # water_level of basins
        water_level = mean_db.joinpath("water_level")
        streamflow = mean_db.joinpath("streamflow")

        # gpm
        gpm_data = mean_db.joinpath("gpm")
        # gfs
        gfs_data = mean_db.joinpath("gfs")
        # mean
        mean_data = mean_db.joinpath("mean")
        
        # basin id
        gauge_id_file = mean_db.joinpath("camels_name.txt")

        return collections.OrderedDict(
            GPM_GFS_DIR=mean_db,
            CAMELS_WATER_LEVEL=water_level,
            CAMELS_STREAMFLOW=streamflow,
            GPM_DATA=gpm_data,
            GFS_DATA=gfs_data,
            MEAN_DATA=mean_data,
            CAMELS_GAUGE_FILE=gauge_id_file,
        )

    def read_site_info(self) -> pd.DataFrame:
        """
        Read the basic information of gages in a CAMELS dataset

        Returns
        -------
        pd.DataFrame
            basic info of gages
        """
        camels_gauge_file = self.data_source_description["CAMELS_GAUGE_FILE"]
        if self.region == "US":
            data = pd.read_csv(
                camels_gauge_file, sep=";", dtype={"gauge_id": str, "huc_02": str}
            )
        else:
            raise NotImplementedError(MEAN_NO_DATASET_ERROR_LOG)
        return data

    def read_object_ids(self, **kwargs) -> np.array:
        """
        read station ids

        Parameters
        ----------
        **kwargs
            optional params if needed

        Returns
        -------
        np.array
            gage/station ids
        """
        if self.region in ["US"]:
            return self.sites["gauge_id"].values
        else:
            raise NotImplementedError(MEAN_NO_DATASET_ERROR_LOG)

    def waterlevel_xrdataset(
        self,
    ):
        """
        convert txt file of water level to a total netcdf file with corresponding time
        """
        # open the waterlevel and gpm files respectively
        waterlevel_path = os.path.join(hds.ROOT_DIR, "gpm_gfs_data", "water_level")
        gpm_path = os.path.join(hds.ROOT_DIR, "gpm_gfs_data", "gpm")
        waterlevel_path_list = os.listdir(waterlevel_path)
        gpm_path_list = os.listdir(gpm_path)

        basin_id_list = []
        waterlevel_array_list = []
        time_fin = []

        for basin_id in gpm_path_list:
            basin_id_list.append(basin_id)
            waterlevel_file = os.path.join(waterlevel_path, str(basin_id) + ".txt")
            df = pd.read_csv(
                waterlevel_file,
                sep="\s+",
                header=None,
                engine="python",
                usecols=[0, 1, 2],
            )
            df.columns = ["date", "time", "water_level"]
            df["datetime"] = df.apply(
                lambda row: " ".join(
                    row[:2],
                ),
                axis=1,
            )
            df = df.drop(columns=[df.columns[0], df.columns[1]])
            df = df[df.columns[::-1]]
            df["datetime"] = df["datetime"].str.slice(0, 19)

            id = waterlevel_path_list.index(basin_id)
            gpm_file = os.path.join(gpm_path, str(waterlevel_path_list[id][:-4]))
            gpm_file_list = os.listdir(gpm_file)
            time_list = []
            for time in gpm_file_list:
                datetime = time[0:19]
                time_list.append(datetime)
            time_df = pd.DataFrame(time_list, columns=["datetime"])

            df_fin = pd.merge(df, time_df, how="right", on="datetime")
            df_fin["datetime"] = pd.to_datetime(df_fin["datetime"])
            df_fin = df_fin.sort_values("datetime")

            waterlevel_array_list.append(df_fin[["water_level"]].values)
            time_fin.append(df_fin["datetime"].values)

        waterlevel_merged_array = np.concatenate(waterlevel_array_list, axis=1)
        ds = xr.Dataset(
            {
                "waterlevel": (["time", "basin"], waterlevel_merged_array),
            },
            coords={"time": time_fin[0], "basin": basin_id_list},
        )

        ds.to_netcdf(os.path.join(hds.ROOT_DIR, "gpm_gfs_data", "water_level_total.nc"))

    def gpm_xrdataset(self):
        gpm_path = os.path.join(hds.ROOT_DIR, "gpm_gfs_data", "gpm")
        gpm_path_list = os.listdir(gpm_path)

        gpm_whole_path = os.path.join(hds.ROOT_DIR, "gpm_gfs_data", "gpm_whole")
        gpm_whole_path_list = os.listdir(gpm_whole_path)
        gpm_whole_path_list_tmp = []
        for path in gpm_whole_path_list:
            gpm_whole_path_list_tmp.append(path[:-3])
        gpm_path_list = list(set(gpm_path_list) - set(gpm_whole_path_list_tmp))

        if len(gpm_whole_path_list_tmp) != 0:
            for basin in gpm_path_list:
                total_data = []
                gpm_list = os.listdir(os.path.join(gpm_path, str(basin)))

                for gpm in gpm_list:
                    single_data_path = os.path.join(gpm_path, str(basin), gpm)
                    single_data = xr.open_dataset(single_data_path)
                    total_data.append(single_data)

                da = xr.concat(total_data, dim="time")

                da_sorted = da.sortby("time")

                da_sorted.to_netcdf(
                    os.path.join(hds.ROOT_DIR, "gpm_gfs_data", "gpm_whole", str(basin))
                    + "nc"
                )

    def read_waterlevel_xrdataset(
        self, gage_id_lst=None, t_range: list = None, var_list=None, **kwargs
    ):
        if var_list is None or len(var_list) == 0:
            return None

        folder = os.path.exists(
            os.path.join("/ftproot", "gpm_gfs_data", "water_level_total.nc")
        )
        if not folder:
            self.waterlevel_xrdataset()

        waterlevel = xr.open_dataset(
            os.path.join("/ftproot", "gpm_gfs_data", "water_level_total.nc")
        )
        all_vars = waterlevel.data_vars
        if any(var not in waterlevel.variables for var in var_list):
            raise ValueError(f"var_lst must all be in {all_vars}")
        return waterlevel[["waterlevel"]].sel(
            time=slice(t_range[0], t_range[1]), basin=gage_id_lst
        )

    def read_gpm_xrdataset(
        self,
        gage_id_lst: list = None,
        t_range: list = None,
        var_lst: list = None,
        **kwargs,
    ):
        if var_lst is None:
            return None

        gpm_dict = {}
        for basin in gage_id_lst:
            gpm = xr.open_dataset(
                os.path.join("/ftproot", "gpm_gfs_data_24h_re", str(basin) + ".nc")
            )
            gpm = gpm[var_lst].sel(time=slice(t_range[0], t_range[1]))
            gpm_dict[basin] = gpm

        return gpm_dict

    def read_streamflow_xrdataset(
        self, gage_id_lst=None, t_range: list = None, var_list=None, **kwargs
    ):
        if var_list is None or len(var_list) == 0:
            return None

        # folder = os.path.exists(
        #     os.path.join("/ftproot", "gpm_gfs_data", "streamflow_total.nc")
        # )
        # if not folder:
        #     self.waterlevel_xrdataset()

        streamflow = xr.open_dataset(
            os.path.join("/ftproot", "LSTM_data", "nldas_hourly.nc")
        )
        all_vars = streamflow.data_vars
        if any(var not in streamflow.variables for var in var_list):
            raise ValueError(f"var_lst must all be in {all_vars}")
        return streamflow[["streamflow"]].sel(
            time=slice(t_range[0], t_range[1]), basin=gage_id_lst
        )

    def read_pmean_xrdataset(
        self, gage_id_lst=None, t_range: list = None, var_list=None, **kwargs
    ):
        if var_list is None or len(var_list) == 0:
            return None

        # mean_dict = {}
        # for basin in gage_id_lst:
        #     p_mean = xr.open_dataset(
        #         os.path.join("/ftproot", "LSTM_data", "p_mean.nc")
        #     )
        #     p_mean = p_mean[var_list].sel(time=slice(t_range[0], t_range[1]))
        #     mean_dict[basin] = p_mean
        # return mean_dict
        
        p_mean = xr.open_dataset(
            os.path.join("/ftproot", "LSTM_data", "nldas_hourly.nc")
        )
        all_vars = p_mean.data_vars
        if any(var not in p_mean.variables for var in var_list):
            raise ValueError(f"var_lst must all be in {all_vars}")
        return p_mean[var_list].sel(
            time=slice(t_range[0], t_range[1]), basin=gage_id_lst
        )

    def read_attr_xrdataset(self, gage_id_lst=None, var_lst=None, **kwargs):
        if var_lst is None or len(var_lst) == 0:
            return None
        attr = xr.open_dataset(os.path.join("/ftproot", "camelsus_attributes_us.nc"))
        if "all_number" in list(kwargs.keys()) and kwargs["all_number"]:
            attr_num = map_string_vars(attr)
            return attr_num[var_lst].sel(basin=gage_id_lst)
        return attr[var_lst].sel(basin=gage_id_lst)

    def read_mean_prcp(self, gage_id_lst) -> np.array:
        if self.region in ["US", "AUS", "BR", "GB"]:
            if self.region == "US":
                return self.read_attr_xrdataset(gage_id_lst, ["p_mean"])
            return self.read_constant_cols(
                gage_id_lst, ["p_mean"], is_return_dict=False
            )
        elif self.region == "CL":
            # there are different p_mean values for different forcings, here we chose p_mean_cr2met now
            return self.read_constant_cols(
                gage_id_lst, ["p_mean_cr2met"], is_return_dict=False
            )
        else:
            raise NotImplementedError(MEAN_NO_DATASET_ERROR_LOG)

    def read_area(self, gage_id_lst) -> np.array:
        if self.region == "US":
            return self.read_attr_xrdataset(gage_id_lst, ["area_gages2"])
        else:
            raise NotImplementedError(MEAN_NO_DATASET_ERROR_LOG)