import pandas as pd
x=pd.read_csv('records.csv'); print('latest rows',x.shape); print(x[x.project=='QP-9219'].to_string(index=False))