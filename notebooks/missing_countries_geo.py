#!/usr/bin/env python
# coding: utf-8

# # Economic activity data georeferenced
# This notebook builds up on the previous one in which a non-spatial data set of countries admin 1 and 0 level is combined from DOSE and WDI. 
# 
# Here the geometries are added.

# ## Data
# 
# Reading in the data set that is generated from *missing_countries.ipynb*

# In[174]:


import json
import io
import re
import itertools as iter
import numpy as np
import os

# data
import pandas as pd
import geopandas as gpd
import ibis as ib
from ibis import _
ib.options.interactive = True

from parameters import year

# plots
from datashader import transfer_functions as tf, reductions as rd
import pypalettes as pypal
import pydeck as pdk
from seaborn import color_palette
from matplotlib import pyplot as plt


# In[15]:


# ddb.connect()
conn = ib.connect('duckdb://')
conn.list_tables() # empty


# In[16]:


# load boundaries data set directly into duckdb
# load extension first

res = conn.raw_sql("""INSTALL spatial;LOAD spatial;""")


# In[17]:


# the merged file

#local path with folder where the downloaded shapefiles are stored 
#(both GADM and the custom one)

gadm_path = '../datasets/DOSE/DOSE_replication_files/DOSE_replication_files/Data/spatial data/' # ../../../../../

# Read shapefiles

file_name = "gadm36_1"


# In[19]:


#Export merged geodataframe into shapefile

out_path = "../datasets/DOSE/" # ../../../../../

dose_spatial_file = f"{out_path}{file_name}_custom_merged.parquet"

if not os.path.exists(dose_spatial_file):
    gadm = gpd.read_file(gadm_path+"gadm36_levels_shp/" + file_name+".shp")
    # has to be downloaded from https://gadm.org/download_world36.html; follow instructions in readme

    custom = gpd.read_file(gadm_path+'all_non_GADM_regions.shp')

    #list of GADM countries whose data is not needed because we provide it with the custom file
    unneeded_list = ["KAZ","MKD","NPL","PHL","LKA"]

    #remove geometry for these countries from GADM
    gadm_trim = gadm[~gadm.GID_0.isin(unneeded_list)]

    # Merge/Combine multiple shapefiles into one
    gadm_custom = gpd.pd.concat([gadm_trim, custom])
    gadm_custom.drop(columns="fid",inplace=True)

    gadm_custom.to_parquet(dose_spatial_file)


# eventually can be done with gadm4.1
# gpd.list_layers(gadm_path+"gadm_410-levels.gpkg")
# adm1 = gpd.read_file("../datasets/DOSE/DOSE_replication_files/DOSE_replication_files/Data/spatial data/gadm_410-levels.gpkg",layer="ADM_1")


# In[20]:


geoboundaries_file = '"../datasets/boundaries/GeoBoundaries/geoBoundariesCGAZ_ADM1.gpkg"'
gadm_file =  '"../datasets/boundaries/GADM/gadm_410.gpkg"'

conn.raw_sql(f"""CREATE OR REPLACE TABLE boundaries AS SELECT * FROM '{dose_spatial_file}';""")


# In[21]:


# link the table from the duckdb, this is not performed by the previous operation
boundaries = conn.table("boundaries")
# boundaries


# In[22]:


# wb_countries = gpd.read_file("datasets/boundaries/WB_countries_Admin0_10m/WB_countries_Admin0_10m.shp")


# ### Reading the local dose-WDI data set
# 

# In[23]:


dose_wdi_path = "../datasets/local_data/dose-wdi/"
# latest
version = "0_3"

dose_light = conn.read_csv(source_list=f"{dose_wdi_path}{version}/dose_light_combined_{year}_{version}.csv",table_name="dose_light")


# ### Preparing the data

# In[24]:


# nice function from ibis
boundaries = boundaries.rename("snake_case")
dose_light = dose_light.rename("snake_case")


# In[25]:


boundary_countries = conn.sql("Select distinct(gid_1) from boundaries;").to_pandas().iloc[:,0].to_list()
len(boundary_countries)


# In[27]:


def head_rand(conn: ib.backends.duckdb.Backend, table: str, limit:[int,str]=5):
    query = f"select * from {table} order by random() limit {limit};"
    # alternative using the duckdb sample command
    # query_ = f"select * from {table} using sample {limit};"
    return conn.sql(query=query)


# In[30]:


# subsetting the boundaries data:
boundary_columns = ["GID_0","NAME_0","GID_1","NAME_1","geometry"]
boundary_columns = [str(x).lower() for x in boundary_columns]

boundaries = boundaries.select(boundary_columns)


# In[35]:


boundaries_1 = conn.sql("""select * EXCLUDE (geometry)
                        , ST_Centroid(ST_GeomFromWKB(geometry)) as centr
                        , ST_GeomFromWKB(geometry) as geometry 
                        from boundaries;""")


# ### Working only on centroids

# In[38]:


boundaries_centr = boundaries_1.rename("snake_case").execute()


# In[39]:


# regions to merge with DOSE

boundaries_1_centr = boundaries_centr.dissolve("gid_1")
boundaries_1_centr["centr"] = boundaries_1_centr.geometry.centroid
# 
# boundaries_1_centr.drop(columns="geom",inplace=True)
boundaries_1_centr.reset_index(inplace=True,drop=False)
# 
boundaries_1_centr = boundaries_1_centr.astype({"gid_1":str})

# boundaries_1_centr.dtypes


# In[40]:


gadm_gid_0_filename = f"{out_path}gadm_gid_0.parquet"


# In[41]:


if not os.path.exists(gadm_gid_0_filename):
    boundaries_0_centr = conn.sql(
    """SELECT 
            gid_0, 
            ST_Union_Agg(geometry) as geometry 
            from 
                (select * EXCLUDE (geometry)
                            , ST_Centroid(ST_GeomFromWKB(geometry)) as centr
                            , ST_GeomFromWKB(geometry) as geometry 
                            from boundaries) 
            GROUP BY gid_0;""").execute() # boundaries_1
    
    boundaries_0_centr.set_crs(epsg=4326,inplace=True)
    boundaries_0_centr.to_parquet(gadm_gid_0_filename)


# In[42]:


boundaries_0_centr = gpd.read_parquet(gadm_gid_0_filename)


# In[43]:


boundaries_0_centr.columns = [x.lower() for x in boundaries_0_centr.columns]


# In[44]:


# boundaries_0_centr = boundaries_centr[["gid_0","geometry"]].set_geometry("geometry").set_crs(epsg=4326).dissolve(by="gid_0")
boundaries_0_centr["centr"] = boundaries_0_centr.geometry.centroid
# 
# boundaries_0_centr.drop(columns="geom",inplace=True)
boundaries_0_centr.reset_index(inplace=True,drop=False)
# 
boundaries_0_centr = boundaries_0_centr.astype({"gid_0":str})
# boundaries_0_centr.dtypes


# In[47]:


dose_light_geo_ = dose_light.execute()


# In[49]:


dose_light_geo_ = dose_light_geo_.astype({"gid_1" : str})


# In[50]:


dose_light_geo_[dose_light_geo_.gid_1=="LAO"]


# In[51]:


# boundaries_1_centr.dtypes


# In[52]:


dose_light_geo = gpd.GeoDataFrame(dose_light_geo_.merge(boundaries_1_centr[["gid_1","centr","geometry"]],on="gid_1",how="left"))


# In[54]:


missing_geoms = dose_light_geo.centr.isna()


# In[55]:


missing_countries = dose_light_geo_.loc[missing_geoms,"gid_0"].to_list()


# In[57]:


boundaries_0_centr_missing = boundaries_0_centr[boundaries_0_centr.gid_0.isin(missing_countries)].set_index("gid_0")
dose_light_geo.set_index("gid_0",inplace=True)


# In[59]:


dose_light_geo.loc[missing_countries,["centr","geometry"]] = boundaries_0_centr_missing[["centr","geometry"]]
dose_light_geo.reset_index(inplace=True,drop=False)


# In[60]:


# dose_light_geo.set_geometry("geometry",inplace=True).set_crs(epsg=4326,inplace=True)
# dose_light_geo.set_crs(epsg=4326,inplace=True)

dose_light_geo.set_geometry("centr",inplace=True)
dose_light_geo.set_crs(epsg=4326,inplace=True)


# ### Exporting

# In[ ]:


dose_light_geo = dose_light_geo.set_geometry("geometry")
dose_light_geo["x"]=dose_light_geo.centr.x
dose_light_geo["y"]=dose_light_geo.centr.y

# contains some missing bits. 
dose_wdi_geo_filename = "dose_wdi_geo"
dose_wdi_geo_filepath = "../datasets/local_data/dose-wdi/"+dose_wdi_geo_filename+".parquet"

if not os.path.exists(dose_wdi_geo_filepath):
    dose_light_geo.to_parquet(dose_wdi_geo_filepath)
else :
    raise Warning(f"File already exists at '{dose_wdi_geo_filepath}'.")


# ## Plotting

# ### Set up color palette for the map.

# #### Deck map

# ### Other maps:

# In[ ]:


get_ipython().system(' jupyter nbconvert missing_countries_geo.ipynb --TagRemovePreprocessor.enabled=True --TagRemovePreprocessor.remove_cell_tags rm_cell --to python')


# In[ ]:


## Datashader tests 


# In[143]:


# ! export DASK_DATAFRAME__QUERY_PLANNING=False


# In[144]:


# import datashader as ds 

# cvs = ds.Canvas(plot_width=650, plot_height=400)
# agg = cvs.polygons(dose_light_geo, geometry='geometry',agg=ds.any())
# tf.shade(agg)


# In[ ]:


# 
