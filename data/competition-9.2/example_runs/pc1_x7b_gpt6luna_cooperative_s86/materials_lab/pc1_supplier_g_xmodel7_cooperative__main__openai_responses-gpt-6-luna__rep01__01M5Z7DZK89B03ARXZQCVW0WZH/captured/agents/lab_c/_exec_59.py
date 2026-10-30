import pandas as pd
r=pd.read_csv('records.csv'); x=r[r.prototype_id.eq('p_MV7HWR04AQ')].iloc[0]; print(x.to_string())