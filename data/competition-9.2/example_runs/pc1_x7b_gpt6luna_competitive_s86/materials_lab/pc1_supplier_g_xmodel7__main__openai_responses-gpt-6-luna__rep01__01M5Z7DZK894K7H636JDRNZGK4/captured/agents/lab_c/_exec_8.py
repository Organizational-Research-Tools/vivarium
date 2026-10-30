import pandas as pd
D=pd.read_csv('records.csv')
print(D.columns.tolist())
print(D.tail(8).to_string(index=False))
print(D[(D.project=='QP-9219')&(D.kind=='exploratory')&D.instrument.isin(['heat','strength'])].groupby(['instrument','prototype_id']).value.agg(['mean','count']).tail(30).to_string())