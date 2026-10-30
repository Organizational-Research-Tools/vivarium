import pandas as pd
x=pd.read_csv('records.csv'); print(x[x.prototype_id=='p_17ZCJFZ9DD'].to_string(index=False))