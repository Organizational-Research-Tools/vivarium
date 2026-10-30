import pandas as pd
x=pd.read_csv('records.csv'); print(x.columns.tolist()); print(x[x.prototype_id.isin(['p_0WWHPMM1FD','p_17ZCJFZ9DD'])].drop_duplicates('prototype_id').to_string(index=False))