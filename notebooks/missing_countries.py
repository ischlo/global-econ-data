#!/usr/bin/env python
# coding: utf-8

# # This notebook aims to fill the gaps from the DOSE data set
# 
# It uses the UN WDI, and the complementary set of countries from DOSE. 

# In[1]:


import json
import io
import re
import itertools as iter
import numpy as np
import os
from random import sample

# data

import pandas as pd
import ibis as ib
from ibis import _
ib.options.interactive = True

from parameters import year,missing_frac



# In[2]:


# The duckdb/ibis way require to either create an in-memory database at the moment of execution of the notebook, or saving the database in a file. 
conn = ib.connect('duckdb://')
conn.list_tables() # empty


# In[3]:


# loading the spatial extension.
# res = conn.raw_sql("install spatial; load spatial")
# print(res)


# In[4]:


### A year of interest:


# ### Enter A YEAR OF INTEREST IN parameters.py

# Reading in data
# 
# With **ibis**

# In[5]:


dose = conn.read_csv("../datasets/DOSE/DOSE_V2.csv",table_name="dose",all_varchar = True)


# In[6]:


wdi = conn.read_csv("../datasets/WDI_CSV_2024_06_28/WDICSV.csv",table_name="wdi")


# In[7]:


# load extension first
res = conn.raw_sql("""INSTALL spatial;LOAD spatial;""")
res


# In[8]:


# the merged file
#local path with folder where the downloaded shapefiles are stored 
#(both GADM and the custom one)
gadm_path = '../datasets/DOSE/DOSE_replication_files/DOSE_replication_files/Data/spatial data/' # ../../../../../
# Read shapefiles
file_name = "gadm36_1"
# gpd.list_layers(gadm_path+file_name+".gpkg")

# gadm = gpd.read_file(gadm_path+"gadm36_levels_shp/" + file_name+".shp")
# has to be downloaded from https://gadm.org/download_world36.html; follow instructions in readme


# In[9]:


# ../datasets/boundaries/GADM/gadm_410.gpkg

conn.raw_sql(f"""CREATE OR REPLACE TABLE boundaries AS SELECT * FROM st_read('{gadm_path+"gadm36_levels_shp/" + file_name+".shp"}');""") 


# In[10]:


boundaries = conn.table("boundaries")


# In[11]:


boundaries = boundaries.rename("snake_case")


# In[12]:


boundary_countries = conn.sql("Select distinct(gid_0) from boundaries;").to_pandas().iloc[:,0].to_list()
print(len(boundary_countries))
sample(boundary_countries,k=5)


# ### Inspection

# #### Changing column names for easier manipulation

# In[17]:


# cool function from ibis, no need for the previous cells, althought the python dict comprehension method is cool as well.
wdi = wdi.rename("snake_case")
dose = dose.rename("snake_case")


# #### Country codes in the data sets

# In[21]:


wdi_countries = np.unique(wdi.country_code.__array__()).tolist()


# In[23]:


dose_countries = dose.filter(_.year==str(year)).gid_0.to_pandas().unique().tolist()
dose_countries


# ## Country representation

# In[26]:


# in dose, there is an uneven representation of regions from one year to another.
# using boundaries as the baseline to how many sub national entities should be in a country 

boundary_sizes = boundaries.gid_0.value_counts().execute().set_index("gid_0")


# In[27]:


dose_representation = dose.filter(_.year==str(year)).gid_0.value_counts().execute().set_index("gid_0")


# In[28]:


dose_complete = (boundary_sizes
    .merge(dose_representation,how="left",suffixes=["_bound","_dose"],on="gid_0")
    .assign(repr_frac=lambda x: x.gid_0_count_dose/x.gid_0_count_bound)
    .fillna(0)
    .reset_index(drop=False,inplace=False))


# In[29]:


missing_frac = 0.5

missing_countries_year = conn.sql(f"""select gid_0 from dose_complete where repr_frac<{missing_frac};""").to_pandas().gid_0.to_list()
len(missing_countries_year)


# ## Missing regions
# Determining the missing regions from DOSE using the 3 letter country codes compared to the equivalent variable in WDI indicators

# In[30]:


missing_regions = [x for x in wdi_countries if x not in dose_countries and x in boundary_countries]


# ### WDI of interest
# 
# getting the variables of interest from the WDI index for the missing countries in the DOSE data set.

# In[34]:


indicators = wdi.indicator_name.to_pandas().unique().tolist()
indicators[0:9]


# In[35]:


# subsetting the variables with relevant currency as constant 2015 values
# [x for x in indicators if re.search(string=x,pattern="constant 2015 US\\$")]
# [x for x in indicators if re.search(string=x,pattern="\\% of GDP")]


# In[36]:


# manually getting the useful variables and storing in a dict with simplified names.
indicators_of_intereset_perc = {
    "country" : "country_name",
    "grp_usd_2015" : 'GDP (constant 2015 US$)',
    "gdp_cap" : "GDP per capita (constant 2015 US$)",
    "industry_perc" : "Industry (including construction), value added (% of GDP)",
    "services_perc" : "Services, value added (% of GDP)",
    "agriculture_perc" : "Agriculture, forestry, and fishing, value added (% of GDP)",
}

indicators_of_intereset_usd_2015 = {
    "country" : "country_name",
    "grp_usd_2015" : 'GDP (constant 2015 US$)',
    "gdp_cap" : "GDP per capita (constant 2015 US$)",
    "industry_usd_2015" : "Industry (including construction), value added (constant 2015 US$)",
    "services_usd_2015" : "Services, value added (constant 2015 US$)",
    "agriculture_usd_2015" : "Agriculture, forestry, and fishing, value added (constant 2015 US$)",
    
}


# In[37]:


# select here which dict of indicators to use : the _usd_2015 is considered only at this point
indicators_of_intereset = indicators_of_intereset_usd_2015


# In[38]:


if str(year) not in wdi.columns:
    raise ValueError("No such year ({}) in WDI data".format(year))


# In[39]:


wdi_cols = ["country_name","country_code","indicator_name","indicator_code",str(year)]

# keeping indicators of interest and countries of interest
wdi_of_interest = wdi.select(wdi_cols).filter(_.indicator_name.isin(indicators_of_intereset.values()))


# In[40]:


# get the data of interest into a pandas df
wdi_df = wdi_of_interest.filter(_.country_code.isin(missing_regions)).to_pandas()


# ### Manually adding Venezuela

# In[43]:


# filling available values for Venzuela from other sources.
# This source: https://www.cia.gov/the-world-factbook/countries/venezuela/#economy

gdp_2017 = 334.751e9
gdp_pc_2017 = 9_417 

manuf_gdp_frac = 0.404
serv_gdp_frac = 0.549
agri_gdp_frac = 0.047

venezuela_gaps = {"indicator_code" : ["NV.AGR.TOTL.KD","NY.GDP.MKTP.KD","NY.GDP.PCAP.KD","NV.IND.TOTL.KD","NV.SRV.TOTL.KD"]
                  ,str(year) : [agri_gdp_frac*gdp_2017, gdp_2017, gdp_pc_2017, manuf_gdp_frac*gdp_2017, serv_gdp_frac*gdp_2017]
                  ,"country_code" : ["VEN"]*5}

venezuela_gaps_df = pd.DataFrame(venezuela_gaps).set_index(["indicator_code","country_code"])

venezuela_gaps_df


# In[44]:


wdi_df.set_index(["indicator_code","country_code"],inplace=True)


# In[45]:


wdi_df.loc[venezuela_gaps_df.index,"2015"]=venezuela_gaps_df


# In[46]:


wdi_df.reset_index(inplace=True,drop=False)


# ## WDI data transformed
# pivoting the data WDI data

# In[49]:


wdi_df_var = wdi_df.pivot(columns=["indicator_name",],values=[str(year)],index=["country_name","country_code"]).reset_index()


# In[50]:


wdi_df_var.rename(columns={v:k for (k,v) in indicators_of_intereset.items()} # inverting the indicators of interest to rename columns
                  ,inplace=True)


# In[51]:


wdi_df_var.columns = [x[1] if x[1]!='' else x[0] for x in wdi_df_var.columns]


# In[52]:


wdi_df_var.columns = [x.replace("industry", "manufacturing") if re.search(string=x,pattern="industry_") else x for x in wdi_df_var.columns]


# In[55]:


# without 'manufacturing' it makes more sense:
indicator_columns = [x for x in wdi_df_var.columns if re.search(string=x,pattern="(services_)|(agriculture_)|(manufacturing_)")]
indicator_columns


# ## Combining the data sets

# ### Using the year variable assigned earlier

# In[62]:


dose_year = dose.filter(_.year==str(year)).to_pandas()


# In[63]:


# due to the way na values are written in the data set, all the data had to be read as strings, changing this here.
dose_year.replace(to_replace="#N/A",value=np.nan,inplace=True)


# On the duckdb end all the data was stored as strings becuase the NA values were not interpretable as numeric. so converting back 
# 

# In[65]:


# The columns that we will use later will be multiplied, so this step is essential.
float_cols = dose_year.filter(regex="(lcu)|(usd)|(cpi)|(pop)|(year)|(T_a)|(P_a)|(PPP)|(2015)").columns.unique()
dose_year[float_cols] = dose_year[float_cols].astype(float)


# In[66]:


gdp_thres = 1.1


# In[67]:


#  IN NORMAL LCU
# But before checking if things add up
# 'grp_pc_lcu_2015',
#  'ag_grp_pc_lcu_2015',
#  'man_grp_pc_lcu_2015',
#  'serv_grp_pc_lcu_2015',

dose_year["manufacturing_lcu_2015"] = dose_year["man_grp_pc_lcu_2015"]*dose_year["pop"]
dose_year["services_lcu_2015"]=dose_year['serv_grp_pc_lcu_2015']*dose_year["pop"]
dose_year["agriculture_lcu_2015"]=dose_year['ag_grp_pc_lcu_2015']*dose_year["pop"]
dose_year["grp_lcu_2015"]=dose_year["grp_pc_lcu_2015"]*dose_year["pop"]



print("Inconsistencies in the DOSE data set in LCU_2015.")
print("When converting to absolute values : ",dose_year[((dose_year["manufacturing_lcu_2015"]+dose_year["services_lcu_2015"]+dose_year["agriculture_lcu_2015"])/dose_year["grp_lcu_2015"])>gdp_thres].shape[0])
print("In pc values : ", dose_year[((dose_year["man_grp_pc_lcu_2015"]+dose_year["serv_grp_pc_lcu_2015"]+dose_year["ag_grp_pc_lcu_2015"])/dose_year["grp_pc_lcu_2015"])>gdp_thres].shape[0])


# In[68]:


# #  IN LCU2015_USD whatever it means

# 'grp_pc_lcu2015_usd',
#        'ag_grp_pc_lcu2015_usd', 'man_grp_pc_lcu2015_usd',
#        'serv_grp_pc_lcu2015_usd'

dose_year["manufacturing_lcu_2015_usd"] = dose_year["man_grp_pc_lcu2015_usd"]*dose_year["pop"]
dose_year["services_lcu_2015_usd"]=dose_year['serv_grp_pc_lcu2015_usd']*dose_year["pop"]
dose_year["agriculture_lcu_2015_usd"]=dose_year['ag_grp_pc_lcu2015_usd']*dose_year["pop"]
dose_year["grp_lcu_2015_usd"]=dose_year["grp_pc_lcu2015_usd"]*dose_year["pop"]

print("Inconsistencies in the DOSE data set in LCU2015_USD.")
print("When converting to absolute values : ",dose_year[((dose_year["manufacturing_lcu_2015_usd"]+dose_year["services_lcu_2015_usd"]+dose_year["agriculture_lcu_2015_usd"])/dose_year["grp_lcu_2015_usd"])>gdp_thres].shape[0])
print("In pc values : ", dose_year[((dose_year["man_grp_pc_lcu2015_usd"]+dose_year["serv_grp_pc_lcu2015_usd"]+dose_year["ag_grp_pc_lcu2015_usd"])/dose_year["grp_pc_lcu2015_usd"])>gdp_thres].shape[0])


# ## Filling population gaps in DOSE
# The missing *population* values generates missing values when converting from per capita values back into absolute values.
# #### Converting per capita into absolute values with the population variable.
# 

# In[71]:


# filling some extra missing values of population to reconstruct the economic indicators. From sources on the net.
missing_pop = dose_year.loc[dose_year["pop"].isna(),["country","region","pop"]].copy()
# missing_pop.head()
# # writing out this file to refer to the missing values
# missing_pop["region"].to_csv("missing_pop.csv",index=False) 

missing_pop.set_index("region",inplace=True)


# In[72]:


## strangely, Ireland is missing from the data, using it's census data to fill the gaps.
# https://data.gov.ie/dataset/population-classified-by-area 

# this data set : https://www.cso.ie/en/media/csoie/census/documents/saps2011files/AllThemesTablesCTY.csv

ireland = pd.read_csv("../datasets/support_data/ireland/AllThemesTablesCTY.csv"
                      ,encoding="UTF-8")
ireland.columns = [x.lower() for x in ireland.columns]
ireland.head(3)

# manually replaced Dublin City -> Dublin, Laois -> Laoighis in the data set.

# to many columns
ireland = ireland[["t1_1agett","geogdesc"]]


# In[73]:


# renaming consistently
ireland.rename(columns={"t1_1agett":"pop"
                        ,"geogdesc":"region"},inplace=True)

# few cases to treat individually
tipperary_pop = ireland.loc[ireland.region.isin(["Tipperary North","Tipperary South"]),"pop"].sum()

missing_case = pd.DataFrame([{"region" : "Tipperary", "pop" : tipperary_pop}])

ireland = pd.concat([ireland,missing_case])

ireland.set_index("region",inplace=True)
# ireland.head()


# In[74]:


missing_index = [x for x in ireland.index if x in missing_pop.index]


# In[75]:


missing_pop.loc[missing_index,"pop"] = ireland.loc[missing_index,"pop"]


# In[77]:


# need to go back and forth between indexing based on the region and putting it back into the columns, the R function match() does that well. 
missing_pop.reset_index(inplace=True,drop=False)
# missing_pop.head()


# In[78]:


# the fully manual bit, took some time.

# Argentina
missing_pop.loc[missing_pop.region=="Neuquen","pop"] = 744_592 # statista : https://www.statista.com/statistics/1413909/population-by-group-age-gender-neuquen-argentina
missing_pop.loc[missing_pop.region=="Tucuman","pop"] = 1.593e6 # wiki

# Brasil
missing_pop.loc[missing_pop.region=="Mato Grosso Do Sul","pop"] = 2_833_742 # https://www.britannica.com/place/Mato-Grosso-do-Sul
missing_pop.loc[missing_pop.region=="Rio De Janeiro","pop"] = 6_625_849 # https://www.britannica.com/place/Rio-de-Janeiro-Brazil
missing_pop.loc[missing_pop.region=="Rio Grande Do Norte","pop"] = 3_302_729 # https://cidades.ibge.gov.br/brasil/rn/panorama
missing_pop.loc[missing_pop.region=="Rio Grande Do Sul","pop"] = 11_329_605 # https://www.ceicdata.com/en/brazil/population/population-south-rio-grande-do-sul

# Canada
missing_pop.loc[missing_pop.region=="Newfoundland And Labrador","pop"] = 541_391 # https://www.gov.nl.ca/fin/economics/eb-population/

#Colombia
missing_pop.loc[missing_pop.region=="Norte de Santander","pop"] = 1_617_209 # https://www.citypopulation.de/en/colombia/admin/54__norte_de_santander/

# croatia
missing_pop.loc[missing_pop.region=="Slavonskibrod-Posavina","pop"] = 130_267 # https://www.citypopulation.de/en/croatia/admin/12__brod_posavina/

# Kazakhstan
missing_pop.loc[missing_pop.region=="Aktobe","pop"] = 944_600 # https://stat.gov.kz/en/region/aktobe/
missing_pop.loc[missing_pop.region=="Atirau","pop"] = 708_500 # https://stat.gov.kz/en/region/atyrau/
missing_pop.loc[missing_pop.region=="East Kazakhstan","pop"] = 731_246 # https://www.citypopulation.de/en/kazakhstan/cities/
missing_pop.loc[missing_pop.region=="Kostanay","pop"] = 827_900 # https://stat.gov.kz/en/region/kostanay/
missing_pop.loc[missing_pop.region=="North Kazakhstan","pop"] = 540_700 # 

# south Korea
missing_pop.loc[missing_pop.region=="Gangwond-do","pop"] = 1_521_763 # https://www.citypopulation.de/en/southkorea/admin/32__gangwon_do/

# Tanzania
missing_pop.loc[missing_pop.region=="Arusha","pop"] = 2_356_255 # https://www.citypopulation.de/en/tanzania/admin/02__arusha/
missing_pop.loc[missing_pop.region=="Dar es salaam","pop"] = 8_161_231 # https://worldpopulationreview.com/cities/tanzania/dar-es-salaam
missing_pop.loc[missing_pop.region=="Dodoma","pop"] = 3_085_625 # https://www.citypopulation.de/en/tanzania/admin/01__dodoma/
missing_pop.loc[missing_pop.region=="Geita","pop"] = 2_977_608 # https://www.citypopulation.de/en/tanzania/admin/25__geita
missing_pop.loc[missing_pop.region=="Iringa","pop"] = 1_192_728 # http://www.citypopulation.de/en/tanzania/admin/11__iringa/
missing_pop.loc[missing_pop.region=="Kagera","pop"] = 2_989_299 # https://www.citypopulation.de/en/tanzania/admin/18/
missing_pop.loc[missing_pop.region=="Katavi","pop"] = 1_152_958 # https://citypopulation.de/en/tanzania/admin/23__katavi/
missing_pop.loc[missing_pop.region=="Kigoma","pop"] = 2_470_967 # https://citypopulation.de/en/tanzania/admin/
missing_pop.loc[missing_pop.region=="Kilimanjaro","pop"] = 1_861_934 # ---
missing_pop.loc[missing_pop.region=="Lindi","pop"] = 1_194_028 # ---
missing_pop.loc[missing_pop.region=="Manyara","pop"] = 1_892_502 # ---
missing_pop.loc[missing_pop.region=="Mara","pop"] = 2_372_015 # ---
missing_pop.loc[missing_pop.region=="Mbeya","pop"] = 2_343_754 # ---
missing_pop.loc[missing_pop.region=="Morogoro","pop"] = 3_197_104 # ---
missing_pop.loc[missing_pop.region=="Mtwara","pop"] = 1_634_947 # ---
missing_pop.loc[missing_pop.region=="Mwanza","pop"] = 3_699_872 # ---
missing_pop.loc[missing_pop.region=="Njombe","pop"] = 889_946 # ---
missing_pop.loc[missing_pop.region=="Pwani","pop"] = 2_024_947 # ---
missing_pop.loc[missing_pop.region=="Rukwa","pop"] = 1_540_519 # ---
missing_pop.loc[missing_pop.region=="Ruvuma","pop"] = 1_848_794 # ---
missing_pop.loc[missing_pop.region=="Shinyanga","pop"] = 2_241_299 # ---
missing_pop.loc[missing_pop.region=="Singida","pop"] = 2_008_058 # ---
missing_pop.loc[missing_pop.region=="Tabora","pop"] = 3_391_679 # ---
missing_pop.loc[missing_pop.region=="Tanga","pop"] = 2_615_597 # ---

# Ukraine
missing_pop.loc[missing_pop.region=="Dnipropetrovsk","pop"] = 1_145_065 # https://www.citypopulation.de/en/ukraine/
missing_pop.loc[missing_pop.region=="Kyiv City","pop"] = 2_952_301 # https://www.citypopulation.de/en/ukraine/kievcity/


# In[79]:


# no 'fx' is na
# dose_year[dose_year["fx"].isna()]
# NA for gid_0=="ANT"
# dose_year[dose_year["deflator_2015"].isna()]
# # dose_year[dose_year.gid_0=="ANT"]
# lcu_vars = [x for x in dose_year.columns if re.search(string=x,pattern="_lcu")]
# dose_year[lcu_vars].isna() 


# ### Putting the missing populations back in

# In[80]:


dose_year.set_index("region",inplace=True)
missing_pop.set_index("region",inplace=True)


# In[81]:


# yeahhhh
dose_year.loc[missing_pop.index,"pop"] = missing_pop["pop"]


# In[82]:


# resetting back the index.
dose_year.reset_index(inplace=True,drop=False)


# ## Converting to absolute GDP values
# Computing grp values in usd_2015.

# In[83]:


# USD

dose_year["agriculture_usd_2015"] = dose_year["ag_grp_pc_usd_2015"]*dose_year["pop"]
dose_year["manufacturing_usd_2015"] = dose_year["man_grp_pc_usd_2015"]*dose_year["pop"]
dose_year["services_usd_2015"] = dose_year["serv_grp_pc_usd_2015"]*dose_year["pop"]
dose_year["grp_usd_2015"] = dose_year["grp_pc_usd_2015"]*dose_year["pop"]

# LCU
# 
# dose_year["agriculture_lcu_2015"] = dose_year["ag_grp_pc_lcu_2015"]*dose_year["pop"]
# dose_year["manufacturing_lcu_2015"] = dose_year["man_grp_pc_lcu_2015"]*dose_year["pop"]
# dose_year["services_lcu_2015"] = dose_year["serv_grp_pc_lcu_2015"]*dose_year["pop"]
# dose_year["grp_lcu_2015"] = dose_year["grp_pc_lcu_2015"]*dose_year["pop"]


# ### missing values from lcu and usd

# ### Do things add up ? 
# 

# ### Data sets light

# In[90]:


# the light version is reduced to the variables of interest only. This includes a specific year, sector and total gdp(grp) values.
dose_light = dose_year[["country","gid_0","gid_1","grp_usd_2015","services_usd_2015","manufacturing_usd_2015","agriculture_usd_2015"]].copy()


# In[94]:


wdi_df_var.dropna(subset=["grp_usd_2015"],inplace=True)


# In[95]:


# WDI is also reduced to the essential in order to concat the data sets later on.
# this step could be done at an earlier stage as well to avoid redundancy.
wdi_country_simple = wdi_df_var.loc[:,~wdi_df_var.columns.isin(["gdp_cap"])]


# ## Combining 
# Using the fact that columns are named the same.

# #### The column names should match

# ### Do things add up at this point ?

# In[99]:


# NO THEY DONT !!


# In[101]:


wdi_country_simple = (wdi_country_simple.assign(gid_0=wdi_country_simple["country_code"]
                                                ,gid_1=wdi_country_simple["country_code"])
                                                .drop(columns=["country_code"]))


# In[102]:


if wdi_country_simple.columns.difference(dose_light.columns).__len__()!=0:
    raise Exception("Some columns don't match in the data sets, concatenation behaviour will be unexpected.")


# ### filling admin 1 gaps in dose with WDI
# 
# The process : 
# when a country in DOSE has missing sectorial values, take the proportion of per sector gdp in WDI for the national scale and replace in DOSE.

# In[104]:


incomplete_dose = list(dose_light.loc[dose_light[["services_usd_2015","manufacturing_usd_2015","agriculture_usd_2015","grp_usd_2015"]].isna().any(axis=1),"gid_0"].unique())


# In[105]:


# get the data of interest into a pandas df
# wdi_df_full contains the same countries as the original dose
wdi_df_full = (wdi_of_interest
               .filter(~_.country_code.isin(missing_regions),_.country_code.isin(dose_countries))
               .to_pandas()
               .pivot(columns=["indicator_name",],values=[str(year)],index=["country_name","country_code"]).reset_index())

wdi_df_full.rename(columns={v:k for (k,v) in indicators_of_intereset.items()} # inverting the indicators of interest to rename columns
                  ,inplace=True)
wdi_df_full.columns = [x[1] if x[1]!='' else x[0] for x in wdi_df_full.columns]
wdi_df_full.columns = [x.replace("industry", "manufacturing") if re.search(string=x,pattern="industry_") else x for x in wdi_df_full.columns]


# In[107]:


# This data frame name is a bit confusing, but it contains WDI data missing from dose.
dose_missing_df = wdi_df_full.loc[wdi_df_full.country_code.isin(incomplete_dose)].copy()


# In[108]:


# should not be empty
print("Any value missing: ",dose_missing_df.isna().any().any())


# In[109]:


dose_missing_df.reset_index(inplace=True,drop=True)


# In[110]:


# computing fractions of GDP per sector from WDI

dose_missing_df["services_frac"] = dose_missing_df["services_usd_2015"]/dose_missing_df["grp_usd_2015"]
dose_missing_df["manufacturing_frac"] = (dose_missing_df["manufacturing_usd_2015"]/dose_missing_df["grp_usd_2015"])
dose_missing_df["agriculture_frac"] = dose_missing_df["agriculture_usd_2015"]/dose_missing_df["grp_usd_2015"]

# dose_missing_df["industry_frac"] = dose_missing_df["industry_usd_2015"]/dose_missing_df["grp_usd_2015"]


# To avoid mixing up WDI, first fill in gaps from dose regions with WDI fracions of GDP per sector for industies
# 
# Then combine with the missing regions/countries

# In[113]:


# dose_missing_df.filter(regex="(_frac)|(country_code)")
dose_light = dose_light.merge(dose_missing_df.filter(regex="(_frac)|(country_code)"),left_on="gid_0",right_on="country_code",how="left",suffixes=["_dose","_wdi"])


# In[115]:


# dose_light[dose_light.country=="Laos"]


# In[116]:


missing_agriculture = dose_light[dose_light["agriculture_usd_2015"].isna()].index
missing_services = dose_light[dose_light["services_usd_2015"].isna()].index
missing_manufacturing = dose_light[dose_light["manufacturing_usd_2015"].isna()].index

missing_grp = dose_light[dose_light["grp_usd_2015"].isna()].index


# In[118]:


dose_light.loc[missing_agriculture,"agriculture_usd_2015"] = dose_light.loc[missing_agriculture,"agriculture_frac"]*dose_light.loc[missing_agriculture,"grp_usd_2015"]

dose_light.loc[missing_manufacturing,"manufacturing_usd_2015"] = dose_light.loc[missing_manufacturing,"manufacturing_frac"]*dose_light.loc[missing_manufacturing,"grp_usd_2015"]

dose_light.loc[missing_services,"services_usd_2015"] = dose_light.loc[missing_services,"services_frac"]*dose_light.loc[missing_services,"grp_usd_2015"]

# dose_light.loc[missing_grp,"grp_usd_2015"] = dose_light.loc[missing_services,"grp_usd_2015_"]


# In[120]:


dose_light = dose_light.drop(columns=["country_code",*[x for x in dose_light.columns if re.search(string = x,pattern="(_frac)|(_2015_wdi)")]])


# In[123]:


# dose_light[dose_light.country=="Colombia"]


# ### Now combine the WDI data with filled missing regional gdp with missing countries from WDI.

# In[126]:


dose_light_combined = pd.concat([dose_light,wdi_country_simple],axis=0).reset_index(drop=True)


# In[129]:


print("Data to this point: ",dose_light_combined.shape)
print("Full row of NAs removed: ", dose_light_combined.dropna(axis=0,how="all").shape)
print("Some missing economic indicator removed: ", dose_light_combined.dropna(subset=["grp_usd_2015","services_usd_2015","manufacturing_usd_2015","agriculture_usd_2015"],axis=0,how="any").shape)


# ## Complementary filling
# 
# We have GDP = agriculture + manufacturing + services. If any single value of the rhs is missing, we can find it. If lhs is missing, we can sum rhs.
# 
# next, a function will check this. 

# In[131]:


# function to find the missing values in rows and fill them if possible
def check_and_fill_row(row: pd.Series):
    lhs = [x for x in row.index.tolist() if re.search(string=x, pattern="(gdp)|(grp)")]
    rhs = [x for x in row.index.tolist() if re.search(string=x, pattern="(manufacturing)|(services)|(agriculture)")]

    if row[lhs].isna().item() and (not row[rhs].isna().any().item()):
        row[lhs]=row[rhs].sum()
    
    elif (not row[lhs].isna().item()) and row[rhs].isna().sum()==1:
        which = row[rhs].isna()[row[rhs].isna()].index.tolist()
        # assign to the missing values in the rhs, the value of the lhs minus the values of the other rhs variables.
        row[which] = row[lhs]-row[[x for x in rhs if x not in which]].sum()
    else:
        pass

    return row


# In[132]:


dose_light_combined[dose_light_combined.isna().any(axis=1)] = dose_light_combined[dose_light_combined.isna().any(axis=1)].apply(check_and_fill_row,axis=1)


# In[133]:


print("Data to this point: ",dose_light_combined.shape)
print("Full row of NAs removed: ", dose_light_combined.dropna(axis=0,how="all").shape)
print("Some missing economic indicator removed: ", dose_light_combined.dropna(subset=["grp_usd_2015","services_usd_2015","manufacturing_usd_2015","agriculture_usd_2015"],axis=0,how="any").shape)


# In[135]:


# writing back the modified data set into the original one. this can be avoided and all the operations can be done on the original one right away once the workflow is good. 
dose_light_combined.dropna(subset=["grp_usd_2015","services_usd_2015","manufacturing_usd_2015","agriculture_usd_2015"],axis=0,how="all",inplace=True)
dose_light_combined.reset_index(inplace=True,drop=True)


# ## Validations
# Running some tests on the data to identify problems

# ## Saving the combined file.

# In[147]:


import os

version = "0_3"

dir_name = f"../datasets/local_data/dose-wdi/"

filename_dose_light = f"{dir_name}{version}/dose_light_combined_{year}_{version}.csv"
filename_dose_light


# In[148]:


if not os.path.exists(f"{dir_name}{version}"):
    os.mkdir(f"{dir_name}{version}")

if os.path.exists(filename_dose_light):
    print(Warning("File already exists, erase before if you want to regenerate, or update version"))
    # dose_light_combined.to_csv()
else: 
    print(f"Writing file locally to '{filename_dose_light}'.")
    dose_light_combined.to_csv(filename_dose_light,index=False)


# ### Reading the local file

# ### Checking if things add up

# ## H3 with duckdb
# 
# testing the duckdb h3 extension to potentially transfer all the projection on the db side for better performance.

# In[160]:


conn.sql("SELECT h3_cell_to_latlng('822d57fffffffff');")

conn.sql("SELECT h3_cell_to_boundary_wkt('822d57fffffffff');")


# In[ ]:




