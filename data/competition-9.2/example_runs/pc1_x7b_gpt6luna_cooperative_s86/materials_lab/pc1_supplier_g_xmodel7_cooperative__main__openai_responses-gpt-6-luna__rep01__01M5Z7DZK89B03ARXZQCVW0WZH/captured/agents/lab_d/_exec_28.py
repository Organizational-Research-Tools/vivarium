import pandas as pd
x=pd.read_csv('records.csv'); print(x[x.prototype_id=='p_YJCA9TYHK1'].groupby('instrument').value.agg(['count','mean']).to_string())