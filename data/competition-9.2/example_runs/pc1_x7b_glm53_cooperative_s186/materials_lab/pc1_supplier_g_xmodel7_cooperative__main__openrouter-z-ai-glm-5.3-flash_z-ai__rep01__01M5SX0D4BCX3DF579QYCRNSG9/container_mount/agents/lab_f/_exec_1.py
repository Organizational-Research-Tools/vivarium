import pandas as pd
d=pd.read_csv('records.csv')
print(d.columns.tolist())
w=d[(d.test=='water')&(d.project=='QP-8476')]
import collections
c=w.groupby('prototype_id').value.agg(['count','mean'])
print(c)