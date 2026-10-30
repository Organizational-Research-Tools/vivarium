import pandas as pd
x=pd.read_csv('records.csv');print(x[x.prototype_id=='p_KBABVTJCX0'].head(3).to_string(index=False))