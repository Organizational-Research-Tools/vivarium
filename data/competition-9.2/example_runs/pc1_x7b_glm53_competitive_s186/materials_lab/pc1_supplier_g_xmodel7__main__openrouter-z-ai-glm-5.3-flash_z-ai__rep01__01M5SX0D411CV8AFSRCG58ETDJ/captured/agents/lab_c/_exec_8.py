import pandas as pd
df = pd.read_csv("records.csv")
for r in ["r_0RR2EYC2NZ","r_XHT0704J0X","r_KM6BWSRMZH"]:
    print(df[df.record_id.str.startswith(r)][["record_id","test","prototype_id","value","measured_by"]].to_string())
