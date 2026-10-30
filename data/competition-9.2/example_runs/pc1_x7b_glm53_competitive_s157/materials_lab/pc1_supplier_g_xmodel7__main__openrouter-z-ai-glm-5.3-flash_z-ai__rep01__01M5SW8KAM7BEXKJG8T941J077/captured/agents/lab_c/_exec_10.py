import pandas as pd
df = pd.read_csv('records.csv')
for pref in ['p_S81ACG3TB','p_30J118A5XA','p_HF5CYH76P','p_2V1CHF70SD']:
    sub = df[(df.prototype_id.str.startswith(pref, na=False))&(df.kind=='qualification')]
    print(pref, sub[['record_id','test','value','measured_by','requester']].to_string())
