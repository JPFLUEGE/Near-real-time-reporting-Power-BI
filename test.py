import logging
import requests
import json
import pandas as pd
from datetime import datetime as dt
from sqlalchemy import create_engine
import os
from dotenv import load_dotenv
load_dotenv()


# Retrieving all parks and filtering for European parks
def getParks():
    API_parks = "https://queue-times.com/parks.json"
    parks = []
    
    response = requests.get(API_parks).json()
    for id in response:
        for park in id["parks"]:
            parks.append(park)

    european_parks = [park for park in parks if park["continent"] in ["Europe"]]
    return european_parks

# Passing all parks to API and retrieve all wait times 
def getWaitTimes(parks):
    attractions = []

    for item in parks:
        id = item["id"]
        API_wait_times = f"https://queue-times.com/parks/{id}/queue_times.json"
        response = requests.get(API_wait_times).json()

        #renaming park keys
        item["Park name"] = item.pop("name")
        item["Park id"] = item.pop("id")

        ## two loops necessary as rides are either nested in categories or not
        # rides in categories
        for category in response["lands"]:
            for ride in category["rides"]:
                # getting additionally the park area
                ride["Park area"] = category["name"]
                ride["park"] = item

                attractions.append(ride)
            
        # rides not in categories
        for ride in response["rides"]:
            ride["park"] = item

            attractions.append(ride)

    return attractions

# Sending data to Power BI streaming dataset
def sendPowerBI(df):
    # Add 2 hours for Berlin timezone. Needed for the Power BI streaming dataset only. Streaming dataset ignors the timezone
    df["Last updated by park"] = (pd.to_datetime(df["Last updated by park"], utc=True) + pd.Timedelta(hours=2)).dt.strftime('%Y-%m-%dT%H:%M:%S.%f%z').str.replace(r'(\+|-)(\d{2})(\d{2})$', r'\1\2:\3', regex=True)
    
    # Convert df to json
    data = df.to_json(orient="records")

    # access env variable
    url = os.getenv("PBIKEY")

    headers = {
        "Content-Type": "application/json"
    }

    response = requests.post(url, headers=headers, data=data)

    if response.status_code == 200:
        print("Data sent to Power BI successfully")
    else:
        print(f"Failed to send data: {response.status_code} - {response.text}")



def sendDatabase(df):
    # Access env variable
    DBKEY = os.getenv("DBKEY")

    # Connection string
    engine = create_engine(DBKEY)

    # Drop not needed columns
    df = df.drop(columns=["latitude", "longitude"])

    # Subtracting two hours. Database would save it with timezone but Power BI ignors the timezone.
    # Apparently this only affects Power BI Desktop and Power BI web recognizes the timezone correctly.
    #df["Last updated by park"] = (pd.to_datetime(df["Last updated by park"], utc=True) - pd.Timedelta(hours=2)).dt.strftime('%Y-%m-%dT%H:%M:%S.%f%z').str.replace(r'(\+|-)(\d{2})(\d{2})$', r'\1\2:\3', regex=True)
    
    # Convert column to datetime
    df['Last updated by park'] = pd.to_datetime(df['Last updated by park'])

    # Send data to database table
    df.to_sql('theme_park_attractions', engine, if_exists='replace', index=False)
    print("Data sent to database successfully")




# Retrieving data, unnesting a nested column and renaming
df = pd.DataFrame(getWaitTimes(getParks()))
df = pd.concat([df.drop(columns=["park"]), pd.json_normalize(df["park"])], axis=1)
df["is_open"] = df["is_open"].apply(lambda x: "open" if x == True else "closed")
df = df.rename(columns={"name": "Attraction name", "wait_time": "Waiting time (minutes)", "last_updated": "Last updated by park", "is_open": "Reported as open?", "country": "Country", "continent": "Continent"})
df["Park area"] = df["Park area"].fillna("No area")

## logging
# pd.set_option("display.max_columns", None)
# print(df["Last updated by park"])
# print(df)
# print(df.columns)

sendPowerBI(df)
sendDatabase(df)
