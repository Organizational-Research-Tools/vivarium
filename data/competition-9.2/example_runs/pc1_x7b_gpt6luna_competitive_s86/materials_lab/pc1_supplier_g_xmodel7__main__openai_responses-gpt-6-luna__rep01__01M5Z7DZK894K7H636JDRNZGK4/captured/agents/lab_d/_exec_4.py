import pandas as pd
x=pd.read_csv('records.csv'); print(x[x.project=='QP-9219'].prototype_id.unique()[-10:])