import pandas as pd
df = pd.read_csv('records.csv')
for pid in ['p_DSTFRJN4CR','p_N4RCVZ2GGA','p_HVDW3M3V1Y']:
    sub = df[df.prototype_id==pid]
    print(pid, sub.groupby(['test','measured_by']).size().to_dict())
print(df[df.record_id.str.startswith('r_1RAWJ1AYRS')].to_string())