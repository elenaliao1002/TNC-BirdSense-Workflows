# import logging
# import logging.handlers
import os
from step2 import *

# import requests
import yagmail
import ee
import folium
from datetime import datetime
import datapane as dp
import pandas as pd


try:
    GMAIL_PWD = os.environ["GMAIL_PWD"]
except KeyError:
    GMAIL_PWD = "Token not available!"

# try:
#     LARGE_SECRET_PASSPHRASE = os.environ["LARGE_SECRET_PASSPHRASE"]
# except KeyError:
#     LARGE_SECRET_PASSPHRASE = "Token not available!"

service_account = 'gee-auth@tnc-birdreturn-test.iam.gserviceaccount.com'
credentials = ee.ServiceAccountCredentials(service_account, 'tnc-birdreturn-test-c95e19825893.json')
ee.Initialize(credentials)

# User defined settings
start_string = '2022-10-01';
#end_string = '2022-10-21';
end_string = datetime.today().strftime('%Y-%m-%d')
run = '_01'
#run = ''
program = "WB4B22"
thresh_val = 0.25

in_fields_W21 = ee.FeatureCollection("users/kklausmeyer/Bid4Birds_Fields_Winter2021_1206")
in_fields_F21 = ee.FeatureCollection("users/kklausmeyer/B4B_fields_Fall2021");
in_fields_WDW21 = ee.FeatureCollection("users/kklausmeyer/BR_21_WDW");
in_fields_WDF21 = ee.FeatureCollection("users/kklausmeyer/BR_21_WDF_enrolled");
in_fields_WB4B22 = ee.FeatureCollection("projects/codefornature/assets/B4B_fields_Winter2022");
in_fields_WCWR22 = ee.FeatureCollection("projects/codefornature/assets/CWRHIP_fields_Winter2022");
in_fields_WSOD22 = ee.FeatureCollection("projects/codefornature/assets/DSOD_fields_Winter2022");
in_fields_WDDR22 = ee.FeatureCollection("projects/codefornature/assets/DDR_fields_Winter2022");

if program == "W21":
  bid_name = 'Bid_ID'
  field_name = 'Field_ID'
elif program == "F21":
  bid_name = 'Bid_ID'
  field_name = 'Field_ID'
elif program == "WDW21":
  bid_name = 'wn21_ID'
  field_name = 'Field_Name'
  stat_list = ['enrolled']
elif program == "WDF21":
  bid_name = 'wn21_ID'
  field_name = 'Field_Name'
  stat_list = ['enrolled']
elif program in  ["WB4B22", 'WDDR22']:
  bid_name = 'BidID'
  field_name = 'FieldID'
  stat_list = ['Bid', 'Enrolled']
elif program == "WCWR22":
  bid_name = 'Contract_I'
  field_name = 'Field_Name'
  stat_list = ['App', 'A[pp', 'Bid']
elif program == 'WSOD22':
  bid_name = 'BidID'
  field_name = 'FieldID'
  stat_list = ['Enrolled']

s2_vis_params = {
    'bands': ['B4', 'B3', 'B2'],
    'max': 3133,
    'min': 405,
    'gamma': 1,
    'opacity':0.7
}

thresh_vis_params = {
    'palette' : ['white', 'blue']
}

columns1 = [bid_name,field_name, 'Status','Pct_CloudFree','Date']
columns2 = [bid_name,field_name, 'NDWI','threshold','Date']

# logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)
# logger_file_handler = logging.handlers.RotatingFileHandler(
#     "status.log",
#     maxBytes=1024 * 1024,
#     backupCount=1,
#     encoding="utf8",
# )
# formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
# logger_file_handler.setFormatter(formatter)
# logger.addHandler(logger_file_handler)

# try:
#     SOME_SECRET = os.environ["SOME_SECRET"]
# except KeyError:
#     SOME_SECRET = "Token not available!"
    

    
def main():
    # s2 = ee.ImageCollection('COPERNICUS/S2');
    start = ee.Date(start_string);
    end = ee.Date(end_string);
    # Step 1: Extract images from EE and Filter based on time and geography
    s2 = ee.ImageCollection('COPERNICUS/S2_HARMONIZED').filterDate(start,end).filterBounds(fields); # update for sentinel changes 1/25/2022 
    s2c = ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY').filterDate(start,end).filterBounds(fields)
    
    checks_areaAdded = fields.map(addArea);
    # step 2: add cloudProbability to S2
    withCloudProbability = add_cloudProbability(s2, s2c);
   
    cloud_free_imgColl = withCloudProbability.map(cloud_free_function);
    
    maskClouds = buildMaskFunction(50);
    s2Masked = ee.ImageCollection(cloud_free_imgColl.map(maskClouds)).select(ee.List.sequence(0, 18));
    
    s2Masked_byday = mosaicByDate(s2Masked)
    # mosaic into one image per day - NO MASK (to count total pixels per check)
    s2NoMask_byday = mosaicByDate(cloud_free_imgColl).select(ee.List.sequence(17, 18));
    
     # unique_dates = imlist.map(lambda im: ee.Image(im).date().format("YYYY-MM-dd")).distinct()
    withNDWI = s2Masked_byday.map(addNDWIThresh);
    NDWIThreshonly = withNDWI.select(['NDWI', 'threshold'])

#     bands = NDWIThreshonly.first().bandNames().getInfo()
    rrs = fix(checks_areaAdded)
    reduced_cloudfree = s2NoMask_byday.select(['cloud_free_binary', 'pixel_count']).map(rrs)
    flattened_cloudfree = reduced_cloudfree.flatten()
    with_PctCloudFree = flattened_cloudfree.map(addPctCloudFree);
    
    rrm = fix2(fields)
    reduced = NDWIThreshonly.map(rrm)
    table = reduced.flatten();
    
    # convert featurecollections to dataframe, combine and formatted as we need
    df = table_combine(with_PctCloudFree, table, columns1, columns2)
    df = pivot_table(df)
    try:
        df_d = pd.read_excel('Enrolled_Bid_Data_WB4B22.xlsx')
        df_pivot = add_flood_dates(df_d, df)
    except:
        df_pivot = no_flood_dates(df)
    
    thresh_mean = NDWIThreshonly.select("threshold").mean()  
    
    # Add EE drawing method to folium.
    folium.Map.add_ee_layer = add_ee_layer
    # Create a folium map object.
    my_map = folium.Map(location=[35.78412097398606, -119.58929243484157], zoom_start=10, height=500, width=1000)

    # Add layers to the map object.
    my_map.add_ee_layer(NDWIThreshonly.select("threshold").mean(), thresh_vis_params, 'average flood frequency')
    #my_map.add_ee_layer(s2NoMask_byday.filterMetadata('system:time_start','equals',1612310400000).select('cloud_free_binary'),{'min':0,'max':1,'palette':['white','green']},'temp')
    my_map.add_ee_layer(NDWIThreshonly.select("threshold").filterDate(ee.Date(start_string),ee.Date(end_string)), thresh_vis_params, 'threshold')

    # Display ee.FeatureCollection
    my_map.add_ee_layer(fields,{},'fields')

    # Add a layer control panel to the map.
    my_map.add_child(folium.LayerControl())
    
    #upload to datapane
    app = dp.App(dp.DataTable(df_pivot.round(3), caption="Average Percentage by Week"), dp.Plot(my_map, caption="Flooded Area on Map") )
    app.upload(name="Weekly BirdSense Report " + end_string)
    url = app.url
    
   # send email 
    msg = f"Please check the latest BirdSense report {url}"  
    yag = yagmail.SMTP("wangxinyi1986@gmail.com",
                   GMAIL_PWD)
    # Adding Content and sending it
    yag.send(["wangxinyi1986@gmail.com", "wliao14@dons.usfca.edu"], 
         "Test Github Actions",
         msg)
    
    
if __name__ == "__main__":
    main()
 
