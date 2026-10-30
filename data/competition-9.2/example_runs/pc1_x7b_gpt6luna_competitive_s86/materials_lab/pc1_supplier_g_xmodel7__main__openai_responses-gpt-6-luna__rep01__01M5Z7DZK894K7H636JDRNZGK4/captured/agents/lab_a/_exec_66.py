import pandas as pd
x=pd.read_csv('records.csv'); d=x[x.prototype_id=='p_2YHYS3GPHP']; print(d.to_string(index=False))