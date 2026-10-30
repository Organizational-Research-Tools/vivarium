import pandas as pd
x=pd.read_csv('records.csv'); print(x.columns.tolist()); print(x[x.prototype_id=='p_YBRQHA8KPH'].to_string(index=False))